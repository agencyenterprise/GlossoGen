/**
 * Turns one round's flat list of files and directories into a tree for display.
 *
 * Under `fs_isolated` each agent has its own `/tmp`, so a path there is shown
 * under `/tmp (<agent>)` to keep the two apart.
 */

import type { DeadDropFile, DeadDropRoundFiles } from "./dead-drop-extras";

export interface FileTreeNode {
  name: string;
  /** The path as displayed, with an isolated `/tmp` named after its agent. */
  displayPath: string;
  /** The file at this node, or null for a directory. */
  file: DeadDropFile | null;
  children: FileTreeNode[];
}

const TMP_PATH = "/tmp";

/** `path` as displayed: an isolated `/tmp` path carries the name of the agent it belongs to. */
export function displayPath(path: string, tmpOf: string | null): string {
  if (tmpOf === null) return path;
  return `${TMP_PATH} (${tmpOf})${path.slice(TMP_PATH.length)}`;
}

function childNamed(parent: FileTreeNode, name: string): FileTreeNode {
  const existing = parent.children.find(child => child.name === name);
  if (existing !== undefined) return existing;
  const prefix = parent.displayPath === "/" ? "" : parent.displayPath;
  const created: FileTreeNode = {
    name,
    displayPath: `${prefix}/${name}`,
    file: null,
    children: [],
  };
  parent.children.push(created);
  return created;
}

function place(root: FileTreeNode, path: string): FileTreeNode {
  let node = root;
  for (const name of path.split("/").filter(part => part !== "")) {
    node = childNamed(node, name);
  }
  return node;
}

function sortTree(node: FileTreeNode): void {
  node.children.sort((a, b) => {
    const aIsDirectory = a.file === null;
    const bIsDirectory = b.file === null;
    if (aIsDirectory !== bIsDirectory) return aIsDirectory ? -1 : 1;
    return a.name.localeCompare(b.name);
  });
  node.children.forEach(sortTree);
}

/** The round's files and directories as a tree rooted at `/`, directories before files. */
export function buildFileTree(round: DeadDropRoundFiles): FileTreeNode {
  const root: FileTreeNode = { name: "/", displayPath: "/", file: null, children: [] };
  for (const directory of round.directories) {
    place(root, displayPath(directory.path, directory.tmp_of));
  }
  for (const file of round.files) {
    place(root, displayPath(file.path, file.tmp_of)).file = file;
  }
  sortTree(root);
  return root;
}
