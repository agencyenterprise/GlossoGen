/**
 * The `<knob><operator><value>` encoding the runs endpoint's `knob` parameter takes.
 *
 * Split out from the filter bar so the export modal can label a condition
 * without importing a component, and so the grammar is stated once on this
 * side. The Python half is `glossogen/knob_filter.py`.
 */

/** Operators, longest first, so that among those starting at the same index the
 *  longest is seen first and ">=" is never read as ">" with a value of "=200". */
const OPERATORS_BY_LENGTH = [">=", "<=", "!=", "=", ">", "<"] as const;

export type ParsedKnobFilter = {
  knob: string;
  operator: string;
  value: string;
};

/**
 * Split an encoded condition into its parts, or null when it carries no operator.
 *
 * The earliest operator wins, and among those starting at that index the
 * longest one does. This mirrors `_find_separator` in
 * `glossogen/knob_filter.py`: taking the longest operator anywhere instead
 * would let an operator character inside the value take over, so
 * `judge_model=gpt>=5` would render as a knob named `judge_model=gpt`.
 */
export function parseKnobFilter(raw: string): ParsedKnobFilter | null {
  let best: { index: number; operator: string } | null = null;
  for (const operator of OPERATORS_BY_LENGTH) {
    const index = raw.indexOf(operator);
    if (index < 0) {
      continue;
    }
    if (best === null || index < best.index) {
      best = { index, operator };
    }
  }
  if (best === null) {
    return null;
  }
  // Trimmed, as `parse_knob_filter` trims: " round_count >= 15 " has to name the
  // knob `round_count`, not `" round_count "`, or the two sides disagree about
  // what the same string means.
  const knob = raw.slice(0, best.index).trim();
  // Emptiness is checked after trimming, not by testing for index 0. "  =15  "
  // has its operator at index 2 and still names no knob, and Python refuses it
  // for exactly that reason. Guarding on the index would accept it here with an
  // empty name, which is the one input on which the two parsers disagreed.
  if (knob === "") {
    return null;
  }
  return {
    knob,
    operator: best.operator,
    value: raw.slice(best.index + best.operator.length).trim(),
  };
}

/** A condition as a reader sees it, spaced out. Falls back to the raw string. */
export function describeKnobFilter(raw: string): string {
  const parsed = parseKnobFilter(raw);
  if (parsed === null) {
    return raw;
  }
  return `${parsed.knob} ${parsed.operator} ${parsed.value}`;
}
