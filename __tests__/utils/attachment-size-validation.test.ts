import { describe, expect, it } from "vitest";
import {
  validateFiles,
  validateIndividualFileSizes,
  validateTotalFileSize,
} from "#/utils/file-validation";

const MEBIBYTE = 1024 * 1024;
const FILE_LIMIT = 50 * MEBIBYTE;

function fileWithSize(name: string, size: number): File {
  const file = new File([], name);
  Object.defineProperty(file, "size", { value: size });
  return file;
}

// @spec ATT-001 — Chat attachments allow 50 MiB per file and 100 MiB combined
describe("attachment size validation", () => {
  it("accepts a file at the 50 MiB boundary and rejects one byte over it", () => {
    expect(
      validateIndividualFileSizes([fileWithSize("at-limit.zip", FILE_LIMIT)]),
    ).toEqual({ isValid: true });

    expect(
      validateIndividualFileSizes([
        fileWithSize("over-limit.zip", FILE_LIMIT + 1),
      ]),
    ).toEqual({
      isValid: false,
      errorMessage: "Files exceeding 50MB are not allowed: over-limit.zip",
      oversizedFiles: ["over-limit.zip"],
    });
  });

  it("reports every oversized file by name in selection order", () => {
    const result = validateIndividualFileSizes([
      fileWithSize("first.bin", FILE_LIMIT + 1),
      fileWithSize("allowed.bin", FILE_LIMIT),
      fileWithSize("second.bin", 60 * MEBIBYTE),
    ]);

    expect(result).toEqual({
      isValid: false,
      errorMessage:
        "Files exceeding 50MB are not allowed: first.bin, second.bin",
      oversizedFiles: ["first.bin", "second.bin"],
    });
  });

  it("accepts new and existing files whose combined size is exactly 100 MiB", () => {
    expect(
      validateTotalFileSize(
        [fileWithSize("new.bin", 50 * MEBIBYTE)],
        [fileWithSize("existing.bin", 50 * MEBIBYTE)],
      ),
    ).toEqual({ isValid: true });
  });

  it("rejects a new and existing aggregate one byte over the limit", () => {
    expect(
      validateTotalFileSize(
        [fileWithSize("new.bin", 50 * MEBIBYTE + 1)],
        [fileWithSize("existing.bin", 50 * MEBIBYTE)],
      ),
    ).toEqual({
      isValid: false,
      errorMessage:
        "Total file size would be 100.0MB, exceeding the 100MB limit. Please select fewer or smaller files.",
    });
  });

  it("formats an oversized aggregate to one decimal place", () => {
    expect(
      validateTotalFileSize(
        [fileWithSize("new.bin", 50 * MEBIBYTE)],
        [fileWithSize("existing.bin", 50.25 * MEBIBYTE)],
      ),
    ).toEqual({
      isValid: false,
      errorMessage:
        "Total file size would be 100.3MB, exceeding the 100MB limit. Please select fewer or smaller files.",
    });
  });

  it("uses an empty existing-file list when none is provided", () => {
    expect(
      validateTotalFileSize([fileWithSize("new.bin", 101 * MEBIBYTE)]),
    ).toEqual({
      isValid: false,
      errorMessage:
        "Total file size would be 101.0MB, exceeding the 100MB limit. Please select fewer or smaller files.",
    });
  });

  it("returns the individual-file error before the aggregate-size error", () => {
    expect(
      validateFiles(
        [fileWithSize("too-large.bin", FILE_LIMIT + 1)],
        [fileWithSize("existing.bin", MEBIBYTE)],
      ),
    ).toEqual({
      isValid: false,
      errorMessage: "Files exceeding 50MB are not allowed: too-large.bin",
      oversizedFiles: ["too-large.bin"],
    });
  });

  it("checks the aggregate after every new file passes individually", () => {
    expect(
      validateFiles([
        fileWithSize("first.bin", 50 * MEBIBYTE),
        fileWithSize("second.bin", 50 * MEBIBYTE),
        fileWithSize("third.bin", MEBIBYTE),
      ]),
    ).toEqual({
      isValid: false,
      errorMessage:
        "Total file size would be 101.0MB, exceeding the 100MB limit. Please select fewer or smaller files.",
    });
  });

  it("accepts an aggregate at the limit through the combined validator", () => {
    expect(
      validateFiles(
        [fileWithSize("new.bin", 50 * MEBIBYTE)],
        [fileWithSize("existing.bin", 50 * MEBIBYTE)],
      ),
    ).toEqual({ isValid: true });
  });
});
