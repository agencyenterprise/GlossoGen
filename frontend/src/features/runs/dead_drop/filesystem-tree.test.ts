import { describe, expect, it } from "vitest";
import type { DeadDropFile, DeadDropRoundFiles } from "./dead-drop-extras";
import { buildFileTree, displayPath, type FileTreeNode } from "./filesystem-tree";

function file(path: string, tmpOf: string | null): DeadDropFile {
  return {
    path,
    tmp_of: tmpOf,
    content: "",
    authors: [],
    readers: [],
    last_changed_by: "ana",
    last_changed_round: 1,
  };
}

function names(node: FileTreeNode): string[] {
  return node.children.map(child => child.name);
}

function child(node: FileTreeNode, name: string): FileTreeNode {
  const found = node.children.find(candidate => candidate.name === name);
  if (found === undefined) throw new Error(`no child ${name} under ${node.displayPath}`);
  return found;
}

describe("filesystem tree", () => {
  it("nests files under their directories, directories first", () => {
    const round: DeadDropRoundFiles = {
      round_number: 1,
      directories: [
        { path: "/home", tmp_of: null },
        { path: "/home/ana", tmp_of: null },
        { path: "/tmp", tmp_of: null },
      ],
      files: [file("/tmp/z.txt", null), file("/tmp/drop/a.txt", null), file("/etc/passwd", null)],
    };
    const root = buildFileTree(round);
    expect(names(root)).toEqual(["etc", "home", "tmp"]);
    const tmp = child(root, "tmp");
    expect(names(tmp)).toEqual(["drop", "z.txt"]);
    const drop = child(tmp, "drop");
    expect(drop.file).toBeNull();
    expect(child(drop, "a.txt").displayPath).toBe("/tmp/drop/a.txt");
    expect(child(drop, "a.txt").file?.path).toBe("/tmp/drop/a.txt");
  });

  it("keeps each agent's isolated /tmp apart", () => {
    expect(displayPath("/tmp/x", "ben")).toBe("/tmp (ben)/x");
    expect(displayPath("/tmp", "ana")).toBe("/tmp (ana)");
    expect(displayPath("/tmp/x", null)).toBe("/tmp/x");
    const round: DeadDropRoundFiles = {
      round_number: 1,
      directories: [
        { path: "/tmp", tmp_of: "ana" },
        { path: "/tmp", tmp_of: "ben" },
      ],
      files: [file("/tmp/x", "ana"), file("/tmp/x", "ben")],
    };
    const root = buildFileTree(round);
    expect(names(root)).toEqual(["tmp (ana)", "tmp (ben)"]);
    expect(child(child(root, "tmp (ana)"), "x").file?.tmp_of).toBe("ana");
    expect(child(child(root, "tmp (ben)"), "x").file?.tmp_of).toBe("ben");
  });
});
