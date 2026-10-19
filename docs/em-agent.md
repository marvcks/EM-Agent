# EM-Agent 界面定制

这是 `marvcks/EM-Agent` 中维护 EM-Agent 界面的分支。代码来自 OpenHands
Agent Canvas，保留其 Agent、工作区、文件、终端、模型配置和自动化功能。

## 版本与目录

- 定制分支：`codex/em-agent-ui`。
- 上游基线：Canvas **1.27.1**，提交
  `f07aebdf5cdd71f4a05ebcf30f8bef5e4e3b70b9`。
- `origin`：`https://github.com/marvcks/EM-Agent.git`。
- `upstream`：`https://github.com/OpenHands/OpenHands.git`。

这个基线与 huoshan 上已部署界面的源码版本一致。fork 原有的 `main`
保留在它原来的提交；本次迁移没有把最新上游功能一起升级到服务器。

本地克隆目录可以叫 `EM-Agent-OpenHands`，无需与 GitHub 仓库同名。
旧的 Next.js/FastAPI EM-Agent 项目仍是独立仓库。

## 改动位置

- `src/em-agent.css`：侧栏、首页、输入框与移动布局。
- `src/themes/color-theme/definitions/em-agent.ts`：默认浅色主题。
- `src/components/shared/em-workspace-topbar.tsx`：桌面工作台标题栏。
- `src/components/features/home/`：科研首页与介绍。
- `src/components/features/sidebar/`：品牌、导航与手机抽屉。
- `src/i18n/translation.json`：品牌及界面文案。
- `src/themes/terminal-themes.ts`、`src/themes/syntax-highlighter-themes.ts`
  和 `file-diff-viewer.tsx`：新主题对应的终端、代码和差异配色。

主题选择使用 `em-agent-color-theme`，独立保留原来的 OpenHands 主题偏好。
新增文案提供英文和中文，其他语言沿用新增文案的英文值。
OpenHands 的原始许可证与版权声明保留。

## 构建与验证

使用 Node.js 24 或更新版本，在仓库根目录执行：

```sh
ELECTRON_SKIP_BINARY_DOWNLOAD=1 npm ci
npm run make-i18n
npm run check-translation-completeness
npm run typecheck
VITE_BASE_PATH=/canvas npm run build
```

`/canvas` 与当前服务器访问路径一致。生成的静态文件在 `build/`，其中不应
包含任何凭据。翻译文件由 `make-i18n` 生成，不要手动编辑生成文件。
项目的标准开发、Docker 和后端说明继续见原有 README 与 `docs/`。

针对这次界面修改的回归测试：

```sh
npm test -- \
  __tests__/themes/color-themes.test.tsx \
  __tests__/themes/color-theme-runtime.test.tsx \
  __tests__/themes/color-theme-embedding.test.tsx \
  __tests__/components/features/home/home-chat-launcher-failed-launch.test.tsx \
  __tests__/components/features/home/home-header-title.test.tsx \
  __tests__/components/features/sidebar/sidebar.test.tsx \
  __tests__/components/features/sidebar/sidebar-cloud-settings.test.tsx
```

上游 `home-chat-launcher.test.tsx` 中的 automate-mode handoff 测试曾在
原版和定制版均失败；升级时应区分原有问题与新增回归。

## 后续维护

后续界面修改直接提交在这个 fork 中。每次升级先取回上游，并在新的升级
分支上合并、解决冲突和验证：

```sh
git fetch upstream --tags
git switch codex/em-agent-ui
git switch -c codex/upgrade-openhands
```

随后合并选定的稳定版本，检查界面、历史会话、工作区、终端和自动化，再
安排部署。`main` 比当前线上版本更新，升级前需要检查前后端兼容性。

生产部署从这个 fork 的完整提交号构建镜像，流程见
[镜像构建、部署和回滚](em-agent-deployment.md)。当前方案沿用固定摘要的
1.27.1 后端运行镜像，在镜像内构建并替换前端。服务器凭据、数据库和项目
文件保存在宿主机，不属于源码或镜像构建上下文。
