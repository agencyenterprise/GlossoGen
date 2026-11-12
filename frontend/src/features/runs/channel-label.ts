import { humanize } from "./format";

/** The runtime names a direct channel "dm:" followed by its members' agent ids joined
 *  with "+", e.g. "dm:viewer_a_1+viewer_a_2". */
const DIRECT_CHANNEL_PREFIX = "dm:";
const DIRECT_CHANNEL_MEMBER_SEPARATOR = "+";

/** A parenthesised suffix closing a role name, such as " (Team A)". */
const PARENTHESISED_SUFFIX = / \([^()]*\)$/;

type RoleNameOf = (agentId: string) => string;

/** The suffix every name ends with, when they all end with the same parenthesised one. */
function sharedSuffix(names: string[]): string {
  const match = PARENTHESISED_SUFFIX.exec(names[0] ?? "");
  if (match === null || names.length < 2) {
    return "";
  }
  const suffix = match[0];
  if (names.every(name => name.endsWith(suffix))) {
    return suffix;
  }
  return "";
}

/** A direct channel named after its members' roles, or null for any other channel.
 *  A suffix every member shares is written once: "Viewer 1 ↔ Viewer 2 (Team A)". */
function directChannelLabel(channelId: string, roleNameOf: RoleNameOf): string | null {
  if (!channelId.startsWith(DIRECT_CHANNEL_PREFIX)) {
    return null;
  }
  const names = channelId
    .slice(DIRECT_CHANNEL_PREFIX.length)
    .split(DIRECT_CHANNEL_MEMBER_SEPARATOR)
    .map(roleNameOf);
  const suffix = sharedSuffix(names);
  const bareNames = names.map(name => name.slice(0, name.length - suffix.length));
  let separator = ", ";
  if (bareNames.length === 2) {
    separator = " ↔ ";
  }
  return bareNames.join(separator) + suffix;
}

/** A channel's name in a list or heading: its members for a direct channel, its
 *  humanized id for any other. */
export function channelLabel(channelId: string, roleNameOf: RoleNameOf): string {
  return directChannelLabel(channelId, roleNameOf) ?? humanize(channelId);
}

/** A channel's name on a message badge: its members for a direct channel, its id for
 *  any other. */
export function channelTag(channelId: string, roleNameOf: RoleNameOf): string {
  return directChannelLabel(channelId, roleNameOf) ?? channelId;
}
