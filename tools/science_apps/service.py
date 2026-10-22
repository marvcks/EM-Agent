"""EM-Agent's single-server manual scientific jobs; independent of Agent Server.

Run: SCIENCE_SESSION_API_KEY=... python -m uvicorn tools.science_apps.service:app
No LLM calls. Inputs are generated from bounded XYZ/enum parameters, never shell.
"""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import hmac
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import tempfile
import time
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .magus_runner import MODEL_DIR, RUNTIME_PYTHON, validate_search
from .reaction_runner import REACTION_APPS, runtime_available, validate_request, verified_result

from .bde_runner import bde_available, validate_bde, verified_bde
from .mineru_runner import MAX_DOCUMENT_BYTES, mineru_available, validate_document, verified_mineru
from .morphology_runner import morphology_available, validate_morphology, verified_morphology
from .cnt2d_runner import cnt2d_available, validate_cnt2d, verified_cnt2d

PREFIX = '/api/science'
MAX_LOG_BYTES = 10 * 1024 * 1024
TIMEOUT_SECONDS = 900
ACTIVE = {'queued', 'running'}
ELEMENTS = ('H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr Rf Db Sg Bh Hs Mt Ds Rg Cn Nh Fl Mc Lv Ts Og').split()
APPLICATIONS = {
    'cnt2d': {'name': 'CNT 二维导热', 'executable': 'cnt2d-solve', 'methods': ['FEM-P2'], 'bases': [], 'category': 'thermal'},
    'mineru': {'name': 'MinerU', 'executable': 'mineru-parse', 'methods': ['vlm', 'pipeline'], 'bases': [], 'category': 'document'},
    'bde': {'name': 'BDE', 'executable': 'bde-analyze', 'methods': ['ALFABET', 'Psi4'], 'bases': [], 'category': 'bond'},
    'xtb': {'name': 'xTB', 'executable': 'xtb', 'methods': ['GFN2-xTB', 'GFN1-xTB'], 'bases': [], 'category': 'semiempirical'},
    'orca': {'name': 'ORCA', 'executable': 'orca', 'methods': ['r2SCAN-3c', 'HF', 'B3LYP'], 'bases': ['def2-SVP', 'def2-TZVP'], 'category': 'quantum'},
    'gaussian': {'name': 'Gaussian', 'executable': 'g16', 'methods': ['HF', 'B3LYP', 'PBE1PBE'], 'bases': ['STO-3G', '6-31G(d)', 'def2SVP'], 'category': 'quantum'},
    'magus': {'name': 'MAGUS', 'executable': 'magus-mace', 'methods': ['MACE-OFF23'], 'bases': [], 'category': 'crystal'},
    'aizynthfinder': {'name': 'AiZynthFinder', 'executable': 'aizynth-route', 'methods': ['USPTO'], 'bases': [], 'category': 'reaction'},
    'lcms2yield': {'name': 'lcms2yield', 'executable': 'lcms-cf', 'methods': ['UV-CF 20250721'], 'bases': [], 'category': 'reaction'},
    'crystal-morphology': {'name': '晶体形貌判别', 'executable': 'morphology-classify',
                           'methods': ['auto', 'CatBoost', 'LightGBM', 'XGBoost', 'SVM', 'GradientBoosting', 'RandomForest'],
                           'bases': [], 'category': 'crystal'},
}


def application_executable(app_id):
    executable = shutil.which(APPLICATIONS[app_id]['executable'])
    if app_id == 'cnt2d' and not cnt2d_available():
        return None
    if app_id == 'mineru' and not mineru_available():
        return None
    if app_id == 'bde' and not bde_available():
        return None
    if app_id == 'crystal-morphology' and not morphology_available():
        return None
    if app_id in REACTION_APPS and not runtime_available(app_id):
        return None
    if app_id == 'magus' and (not os.access(RUNTIME_PYTHON, os.X_OK) or
            not all((MODEL_DIR / f'MACE-OFF23_{size}.model').is_file() for size in ('small', 'medium', 'large'))):
        return None
    return executable


class JobRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    app_id: Literal['xtb', 'orca', 'gaussian', 'magus', 'aizynthfinder', 'lcms2yield', 'bde', 'mineru', 'crystal-morphology', 'cnt2d']
    cnt_parameters: dict[str, float | int | str] | None = None
    cnt_corners: str = Field(default='', max_length=32768)
    cnt_seed: int = Field(default=20260901, ge=0, le=2147483647)
    document_name: str = Field(default='', max_length=128)
    language: Literal['en', 'ch'] = 'ch'
    enable_formula: bool = True
    enable_table: bool = True
    xyz: str = Field(default='', max_length=65536)
    smiles: str = Field(default='', max_length=32768)
    input_kind: Literal['smiles', 'name'] = 'smiles'
    compound_name: str = Field(default='', max_length=256)
    title: str = Field(default='', max_length=80)
    task: Literal['energy', 'optimize', 'search', 'retrosynthesis', 'correction_factor', 'bde', 'textify', 'classification', 'conduction'] = 'energy'
    method: str = ''
    basis: str = ''
    charge: int = Field(default=0, ge=-10, le=10)
    multiplicity: int = Field(default=1, ge=1, le=5)
    cores: int = Field(default=2, ge=1, le=8)
    memory_mb: int = Field(default=2048, ge=512, le=8192)
    input_mode: Literal['single', 'batch'] = 'single'
    table_csv: str = Field(default='', max_length=32768)
    additive_percent: float | None = Field(default=None, allow_inf_nan=False)
    antisolvent_temp_c: float | None = Field(default=None, allow_inf_nan=False)
    stirring_rpm: float | None = Field(default=None, allow_inf_nan=False)
    concentration_g_ml: float | None = Field(default=None, allow_inf_nan=False)
    solvent_ratio: float | None = Field(default=None, allow_inf_nan=False)
    model_size: Literal['small', 'medium', 'large'] = 'medium'
    molecules_per_cell: int = Field(default=4, ge=1, le=8)
    population_size: int = Field(default=6, ge=4, le=12)
    generations: int = Field(default=3, ge=1, le=10)
    volume_min: float = Field(default=180.0, ge=30, le=20000, allow_inf_nan=False)
    volume_max: float = Field(default=400.0, ge=30, le=20000, allow_inf_nan=False)
    iterations: int = Field(default=100, ge=1, le=500)
    search_seconds: int = Field(default=60, ge=1, le=600)
    max_transforms: int = Field(default=6, ge=1, le=10)
    max_routes: int = Field(default=10, ge=1, le=25)


def now():
    return datetime.now(timezone.utc).isoformat()


def parse_xyz(text, charge, multiplicity):
    lines = text.strip().splitlines()
    try:
        count = int(lines[0])
    except (ValueError, IndexError):
        raise ValueError('invalid_xyz') from None
    if not 1 <= count <= 128 or len(lines) != count + 2:
        raise ValueError('invalid_xyz')
    atoms = []
    electrons = -charge
    for line in lines[2:]:
        parts = line.split()
        if len(parts) != 4 or parts[0] not in ELEMENTS:
            raise ValueError('invalid_xyz')
        try:
            coords = [float(value) for value in parts[1:]]
        except ValueError:
            raise ValueError('invalid_xyz') from None
        if not all(math.isfinite(value) and abs(value) <= 10000 for value in coords):
            raise ValueError('invalid_xyz')
        electrons += ELEMENTS.index(parts[0]) + 1
        atoms.append(parts[0] + ' ' + ' '.join(f'{value:.10f}' for value in coords))
    if electrons < multiplicity - 1 or (electrons - (multiplicity - 1)) % 2:
        raise ValueError('invalid_spin')
    return atoms


def prepare_input(request):
    config = APPLICATIONS[request.app_id]
    method = request.method or config['methods'][0]
    basis = request.basis or (config['bases'][0] if config['bases'] else '')
    if method not in config['methods'] or (basis and basis not in config['bases']):
        raise ValueError('invalid_method')
    if request.app_id == 'cnt2d':
        request.method = method
        validate_cnt2d(request)
        return 'request.json', request.model_dump_json(indent=2), ['request.json']
    if request.app_id == 'mineru':
        if request.task != 'textify' or request.xyz or request.smiles or not request.document_name:
            raise ValueError('invalid_document')
        request.method = method
        return 'request.json', request.model_dump_json(indent=2), ['request.json']
    if request.app_id == 'bde':
        validate_bde(request)
        request.method = method
        return 'request.json', request.model_dump_json(indent=2), ['request.json']
    if request.app_id in REACTION_APPS:
        validate_request(request)
        return 'request.json', request.model_dump_json(indent=2), ['request.json']
    if request.app_id == 'crystal-morphology':
        request.method = method
        validate_morphology(request)
        return 'request.json', request.model_dump_json(indent=2), ['request.json']
    if request.smiles or request.task not in {'energy', 'optimize', 'search'}:
        raise ValueError('invalid_method')
    atoms = parse_xyz(request.xyz, request.charge, request.multiplicity)
    if request.app_id == 'magus':
        validate_search(request.model_dump(), atoms)
        return 'request.json', request.model_dump_json(indent=2), ['request.json']
    if request.task == 'search':
        raise ValueError('invalid_method')
    xyz = f'{len(atoms)}\nEM-Agent manual calculation\n' + '\n'.join(atoms) + '\n'
    geometry = '\n'.join(atoms)
    if request.app_id == 'xtb':
        args = ['input.xyz', '--gfn', '2' if method == 'GFN2-xTB' else '1', '--chrg', str(request.charge), '--uhf', str(request.multiplicity - 1), '--parallel', str(request.cores)]
        if request.task == 'optimize':
            args.append('--opt')
        return 'input.xyz', xyz, args
    if request.app_id == 'orca':
        theory = method if method == 'r2SCAN-3c' else f'{method} {basis}'
        task = 'SP' if request.task == 'energy' else 'Opt'
        content = (f'! {theory} {task}\n%pal nprocs {request.cores} end\n'
                   f'%maxcore {request.memory_mb // request.cores}\n'
                   f'* xyz {request.charge} {request.multiplicity}\n{geometry}\n*\n')
        return 'input.inp', content, ['input.inp']
    task = 'SP' if request.task == 'energy' else 'Opt'
    content = (f'%chk=calculation.chk\n%nprocshared={request.cores}\n%mem={request.memory_mb}MB\n'
               f'#p {method}/{basis} {task}\n\nEM-Agent manual calculation\n\n'
               f'{request.charge} {request.multiplicity}\n{geometry}\n\n')
    return 'input.gjf', content, []


class Manager:
    def __init__(self, root):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.jobs = {}
        self.queue = asyncio.Queue()
        self.process = None
        self.running_id = None
        for metadata in sorted(root.glob('*/job.json')):
            try:
                job = json.loads(metadata.read_text())
                if metadata.parent.name != job['id'] or not re.fullmatch(r'[a-f0-9]{32}', job['id']):
                    continue
                self.jobs[job['id']] = job
                if job['status'] in ACTIVE:
                    job.update(status='failed', error='service_restarted', finished_at=now())
                    self.save(job)
            except (ValueError, KeyError, OSError):
                continue

    def directory(self, job_id):
        if not re.fullmatch(r'[a-f0-9]{32}', job_id):
            raise FileNotFoundError
        return self.root / job_id

    def save(self, job):
        temporary = self.directory(job['id']) / 'job.json.next'
        temporary.write_text(json.dumps(job, ensure_ascii=False, indent=2))
        temporary.replace(temporary.with_name('job.json'))

    def submit(self, request, document=None, *, source: Literal['manual', 'agent'] = 'manual'):
        if sum(job['status'] in ACTIVE for job in self.jobs.values()) >= 10:
            raise HTTPException(429, 'queue_full')
        name, content, _ = prepare_input(request)
        if request.app_id == 'mineru':
            if document is None:
                raise ValueError('invalid_document')
            suffix = validate_document(request.document_name, document)
        executable = application_executable(request.app_id)
        if not executable:
            raise HTTPException(409, 'app_unavailable')
        job_id = uuid4().hex
        directory = self.directory(job_id)
        directory.mkdir(mode=0o700)
        (directory / name).write_text(content)
        if request.app_id == 'mineru':
            (directory / ('document' + suffix)).write_bytes(document)
        if request.xyz:
            (directory / 'structure.xyz').write_text(request.xyz)
        job = {'id': job_id, 'app_id': request.app_id, 'source': source,
               'title': request.title.strip() or APPLICATIONS[request.app_id]['name'],
               'status': 'queued', 'created_at': now(), 'started_at': None, 'finished_at': None,
               'error': None, 'energy_hartree': None, 'energy_ev': None, 'exit_code': None, 'request': request.model_dump()}
        self.jobs[job_id] = job
        self.save(job)
        self.queue.put_nowait(job_id)
        return job

    def get(self, job_id):
        self.directory(job_id)
        if job_id not in self.jobs:
            raise FileNotFoundError
        return self.jobs[job_id]

    def file(self, job_id, name):
        self.get(job_id)
        if Path(name).name != name or name in {'job.json', 'job.json.next'}:
            raise FileNotFoundError
        file = self.directory(job_id) / name
        if file.is_symlink() or not file.is_file() or file.resolve().parent != self.directory(job_id).resolve():
            raise FileNotFoundError
        return file

    def detail(self, job_id):
        job = dict(self.get(job_id))
        directory = self.directory(job_id)
        log = directory / 'output.log'
        if log.is_file():
            with log.open('rb') as stream:
                stream.seek(max(0, log.stat().st_size - 64000))
                job['log'] = stream.read(64000).decode('utf-8', errors='replace')
        else:
            job['log'] = ''
        job['files'] = []
        for path in sorted(directory.iterdir()):
            try:
                safe = self.file(job_id, path.name)
                job['files'].append({'name': path.name, 'size': safe.stat().st_size})
            except FileNotFoundError:
                continue
        return job

    async def terminate(self):
        if self.process is None:
            return
        process = self.process
        try:
            # The program may leave MPI/worker descendants after its leader exits.
            os.killpg(process.pid, signal.SIGTERM)
            await asyncio.sleep(0.15)
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await process.wait()
        except ProcessLookupError:
            pass

    async def cancel(self, job_id):
        job = self.get(job_id)
        if job['status'] in ACTIVE:
            job.update(status='cancelled', finished_at=now())
            self.save(job)
            if self.running_id == job_id:
                await self.terminate()
        return self.detail(job_id)

    async def run(self, job_id):
        job = self.get(job_id)
        if job['status'] != 'queued':
            return
        job.update(status='running', started_at=now())
        self.save(job)
        self.running_id = job_id
        directory = self.directory(job_id)
        request = JobRequest(**job['request'])
        name, _, args = prepare_input(request)
        executable = application_executable(request.app_id)
        # PyTorch multiprocessing uses Unix sockets beneath TMPDIR. Persistent
        # job paths exceed AF_UNIX's path limit, so reaction jobs get a short,
        # private scratch path. The same finally block removes it on stop/failure.
        if request.app_id in REACTION_APPS:
            scratch = Path(tempfile.mkdtemp(prefix='em-science-', dir='/tmp'))
        else:
            scratch = directory / 'scratch'
            scratch.mkdir(exist_ok=True)
        # ORCA uses PAL/MPI workers; each worker must not spawn another cores-sized BLAS pool.
        threads = '1' if request.app_id == 'orca' else str(request.cores)
        environment = {**os.environ, 'OMP_NUM_THREADS': threads, 'OPENBLAS_NUM_THREADS': threads,
                       'MKL_NUM_THREADS': threads, 'PYTHONNOUSERSITE': '1',
                       'GAUSS_SCRDIR': str(scratch.resolve()), 'TMPDIR': str(scratch.resolve())}
        log_path = directory / 'output.log'
        try:
            if not executable:
                raise FileNotFoundError('app_unavailable')
            with log_path.open('wb') as output, (directory / name).open('rb') as input_file:
                self.process = await asyncio.create_subprocess_exec(executable, *args, cwd=directory,
                    env=environment, stdin=input_file if request.app_id == 'gaussian' else asyncio.subprocess.DEVNULL,
                    stdout=output, stderr=asyncio.subprocess.STDOUT, start_new_session=True)
                if job['status'] == 'cancelled':
                    await self.terminate()
                started = time.monotonic()
                waiter = asyncio.create_task(self.process.wait())
                while self.process.returncode is None:
                    # @spec SJT-001 — Agent jobs have no platform duration limit; legacy jobs remain manual
                    timed_out = job.get('source', 'manual') != 'agent' and time.monotonic() - started > TIMEOUT_SECONDS
                    if timed_out or log_path.stat().st_size > MAX_LOG_BYTES:
                        job['error'] = 'timeout' if timed_out else 'output_limit'
                        await self.terminate()
                        break
                    try:
                        await asyncio.wait_for(asyncio.shield(waiter), timeout=0.5)
                    except TimeoutError:
                        continue
                job['exit_code'] = await self.process.wait()
            text = log_path.read_text(errors='replace')
            markers = {'xtb': 'normal termination of xtb', 'orca': 'ORCA TERMINATED NORMALLY', 'gaussian': 'Normal termination of Gaussian', 'magus': 'EM_AGENT_MAGUS_COMPLETE',
                       'aizynthfinder': 'EM_AGENT_REACTION_COMPLETE', 'lcms2yield': 'EM_AGENT_REACTION_COMPLETE', 'bde': 'EM_AGENT_BDE_COMPLETE', 'mineru': 'EM_AGENT_MINERU_COMPLETE',
                       'crystal-morphology': 'EM_AGENT_MORPHOLOGY_COMPLETE', 'cnt2d': 'EM_AGENT_CNT2D_COMPLETE'}
            if job['status'] != 'cancelled':
                success = job['exit_code'] == 0 and markers[job['app_id']].lower() in text.lower() and not job['error']
                if success and job['app_id'] == 'magus':
                    result = json.loads((directory / 'result.json').read_text())
                    success = (result.get('verified') is True and result.get('candidate_count', 0) > 0
                               and result.get('converged_count', 0) > 0
                               and math.isfinite(result.get('energy_eV', float('nan'))))
                    if success:
                        job['energy_ev'] = result['energy_eV']
                if success and job['app_id'] in REACTION_APPS:
                    result = json.loads((directory / 'result.json').read_text())
                    success = verified_result(result, job['app_id'], len(request.smiles.strip().splitlines()))
                    if success:
                        job['result'] = result
                if success and job['app_id'] == 'bde':
                    result = json.loads((directory / 'result.json').read_text())
                    success = verified_bde(result) and result.get('mode') == request.method
                    if success:
                        job['result'] = result
                if success and job['app_id'] == 'mineru':
                    result = json.loads((directory / 'result.json').read_text())
                    success = verified_mineru(result, directory)
                    if success:
                        job['result'] = result
                if success and job['app_id'] == 'crystal-morphology':
                    result = json.loads((directory / 'result.json').read_text())
                    success = verified_morphology(result, request)
                    if success:
                        job['result'] = result
                if success and job['app_id'] == 'cnt2d':
                    result = json.loads((directory / 'result.json').read_text())
                    success = verified_cnt2d(result, request) and (directory / 'results.zip').is_file()
                    if success:
                        job['result'] = result
                job['status'] = 'succeeded' if success else 'failed'
                if not success and not job['error']:
                    job['error'] = 'calculation_failed'
                patterns = {'xtb': r'TOTAL ENERGY\s+(-?[\d.]+)', 'orca': r'FINAL SINGLE POINT ENERGY\s+(-?[\d.]+)',
                            'gaussian': r'SCF Done:.*?=\s*(-?[\d.]+)'}
                energies = re.findall(patterns[job['app_id']], text) if job['app_id'] in patterns else []
                if success and energies:
                    job['energy_hartree'] = float(energies[-1])
        except Exception:
            if job['status'] != 'cancelled':
                job.update(status='failed', error='execution_error')
        finally:
            await self.terminate()
            self.process = None
            self.running_id = None
            job['finished_at'] = now()
            self.save(job)
            shutil.rmtree(scratch, ignore_errors=True)

    async def worker(self):
        while True:
            job_id = await self.queue.get()
            try:
                await self.run(job_id)
            finally:
                self.queue.task_done()


def create_app(root=None, key=None):
    @asynccontextmanager
    async def lifespan(app):
        session_key = key if key is not None else os.environ.get('SCIENCE_SESSION_API_KEY', '')
        if not session_key:
            raise RuntimeError('SCIENCE_SESSION_API_KEY is required')
        app.state.session_key = session_key
        app.state.manager = Manager(root or Path(os.environ.get('SCIENCE_APPS_DATA_DIR', str(Path.home() / '.openhands' / 'science-apps'))))
        worker = asyncio.create_task(app.state.manager.worker())
        try:
            yield
        finally:
            manager = app.state.manager
            if manager.running_id:
                await manager.cancel(manager.running_id)
            worker.cancel()
            try:
                await worker
            except asyncio.CancelledError:
                pass

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware('http')
    async def authenticate(request: Request, call_next):
        supplied = request.headers.get('X-Session-API-Key', '')
        if not hmac.compare_digest(supplied.encode(), app.state.session_key.encode()):
            return JSONResponse({'detail': 'unauthorized'}, status_code=401)
        if request.method == 'POST' and request.url.path != PREFIX + '/documents':
            if int(request.headers.get('content-length', '0')) > 131072:
                return JSONResponse({'detail': 'input_too_large'}, status_code=413)
            if len(await request.body()) > 131072:
                return JSONResponse({'detail': 'input_too_large'}, status_code=413)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.exception_handler(FileNotFoundError)
    async def not_found(request, exc):
        return JSONResponse({'detail': 'not_found'}, status_code=404)

    @app.get(PREFIX + '/health')
    async def health():
        return {'status': 'ok'}

    @app.get(PREFIX + '/apps')
    async def apps(source: Literal['manual', 'agent'] = Header(default='manual', alias='X-EM-Agent-Source')):
        return [{'id': app_id, **{k: v for k, v in config.items() if k != 'executable'},
                 'available': application_executable(app_id) is not None,
                 'max_cores': 8, 'max_memory_mb': 8192,
                 'timeout_seconds': None if source == 'agent' else TIMEOUT_SECONDS} for app_id, config in APPLICATIONS.items()]

    @app.get(PREFIX + '/jobs')
    async def jobs():
        return [{k: v for k, v in job.items() if k != 'request'} for job in sorted(app.state.manager.jobs.values(), key=lambda item: item['created_at'], reverse=True)[:100]]

    @app.post(PREFIX + '/jobs', status_code=201)
    async def submit(request: JobRequest,
                     source: Literal['manual', 'agent'] = Header(default='manual', alias='X-EM-Agent-Source')):
        try:
            return app.state.manager.submit(request, source=source)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    # @spec MINERU-001 — Stream uploads with a hard byte bound, then enqueue atomically
    @app.post(PREFIX + '/documents', status_code=201)
    async def document(request: Request, filename: str, title: str = '',
                       method: Literal['vlm', 'pipeline'] = 'vlm',
                       language: Literal['en', 'ch'] = 'ch',
                       enable_formula: bool = True, enable_table: bool = True,
                       source: Literal['manual', 'agent'] = Header(default='manual', alias='X-EM-Agent-Source')):
        try:
            size = int(request.headers.get('content-length', '0'))
        except ValueError:
            raise HTTPException(422, 'invalid_document') from None
        if size > MAX_DOCUMENT_BYTES:
            raise HTTPException(413, 'input_too_large')
        if not application_executable('mineru'):
            raise HTTPException(409, 'app_unavailable')
        if sum(job['status'] in ACTIVE for job in app.state.manager.jobs.values()) >= 10:
            raise HTTPException(429, 'queue_full')
        data = bytearray()
        async for chunk in request.stream():
            if len(data) + len(chunk) > MAX_DOCUMENT_BYTES:
                raise HTTPException(413, 'input_too_large')
            data.extend(chunk)
        try:
            job_request = JobRequest(app_id='mineru', task='textify', document_name=filename,
                title=title, method=method, language=language, enable_formula=enable_formula,
                enable_table=enable_table, cores=1, memory_mb=512)
            return app.state.manager.submit(job_request, bytes(data), source=source)
        except ValueError:
            raise HTTPException(422, 'invalid_document') from None

    @app.get(PREFIX + '/jobs/{job_id}')
    async def detail(job_id: str):
        return app.state.manager.detail(job_id)

    @app.post(PREFIX + '/jobs/{job_id}/cancel')
    async def cancel(job_id: str):
        return await app.state.manager.cancel(job_id)

    @app.get(PREFIX + '/jobs/{job_id}/files/{name}')
    async def download(job_id: str, name: str):
        return FileResponse(app.state.manager.file(job_id, name), filename=name, media_type='application/octet-stream')

    return app


app = create_app()
