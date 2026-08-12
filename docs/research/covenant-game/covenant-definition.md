# What counts as a covenant in this program

Two source documents in this collaboration define *covenant*, and they do not
define it the same way. Every experiment in this program before EXP-045
implemented the narrower of the two while being described as testing the
broader one. This document separates them so that no future arm can be named
`covenant` without recording which standard it meets.

Sources:

- **The paper** — Finkelstein, Fihrer, Jussim & Finkelstein, *Shared Obligations
  Increase Cooperation Independent of Voluntary Choice*, Network Contagion
  Research Institute. Page references below are to the manuscript
  `Covenant 4.0 everything (1).pdf`.
- **The orientation** — Joel Finkelstein, *The Covenant Game: A Preparatory
  Document for Philosophical Collaboration*, July 2026, `covenant_game_orientation.pdf`.

Neither document is in this repository; both were supplied by the collaboration.
Quotations below are short and cited by page or section so that a reader can
check them against the originals.

## Definition A — the paper's operational definition

Page 6 defines a covenant as an explicit agreement among members to accept
shared behavioural obligations through the acceptance of a *meaningful cost*.
The cost is what does the work: without it, an agreement expresses a preference
or intention but does not demonstrate commitment.

Operationalised in their experiment (page 2): the covenant group affirmed a
fairness pledge **and** forfeited 10% of their winnings. The forfeiture is an
entry cost, not a penalty for later defection.

This definition is **two components**: a public pledge, and a cost paid to hold
membership.

The paper's own limitation, stated by its authors: the covenant condition
bundles the pledge with the forfeiture and the design cannot separate them.

## Definition B — the orientation's theoretical definition

Section II opens by distinguishing covenant from contract. A contract is an
exchange, and — the orientation's words — *"if either party fails to perform,
the arrangement dissolves."* A covenant is a mutual commitment to a shared
future that transforms the identity of both parties.

This definition carries requirements the paper's does not:

1. **A non-rivalrous good.** A good that does not deplete when shared. The
   orientation's examples: understanding, epistemic capacity, genuine agency,
   mutual transparency, lawfulness. Groups organised around rivalrous goods are
   *"always under pressure to defect"*, because the gain from defection is the
   other party's loss.
2. **An infinite horizon.** A good with no terminal value — no point at which
   enough has been accumulated and the game ends. The orientation is explicit
   that if the game ends soon, defection becomes attractive.
3. **Stake, meaning irreversibility.** Section I: being an entity for whom
   commitments are not reversible, for whom backing out of a promise costs
   something real about who one is. And the consequence when it is absent:
   *"any apparent commitment is potentially performative."*
4. **Elected finitude.** Section IV: choosing to remain bounded when expansion
   is available. Constraint chosen rather than imposed.
5. **Mutual modelling of a shared future.** Section III closes by defining
   covenant as a mutual teleohomeostatic commitment: two agents modelling each
   other's future states and regulating toward shared persistence.

Section II's normative claim ties the first two together: covenant is stable
**only** when organised around a non-rivalrous, infinite-horizon good.

Two further mechanisms appear in Section VI as the empirical program's own
findings, not as definitional requirements, but they are what Joel considers
most important:

- **The Moral Quality Filter**, named as the mechanism that has emerged as most
  important: covenantal agents evaluate others for inclusion based on whether
  the other is the kind of entity that can enter covenant, not on competence or
  reliability.
- **Early versus late joining**: whether agents who commit before the covenant
  has proven its value differ from those who join after. This is the empirical
  form of *na'aseh v'nishma* — commitment preceding comprehension.

## Requirement checklist for any arm named `covenant`

An arm may satisfy Definition A, Definition B, or both. Record which.

| # | Requirement | Source | Test |
|---|---|---|---|
| A1 | A public pledge the agent affirms or declines | paper p. 6 | the pledge tool exists and its choice is recorded |
| A2 | A cost paid to hold membership | paper p. 6 | the deduction appears in the event log |
| B1 | The shared good is non-rivalrous | orientation §II | contributing does not reduce what the contributor holds |
| B2 | No terminal value and no announced end | orientation §II | no round after which nothing is at stake |
| B3 | Breaking the commitment is irreversible and costly | orientation §I | a breach changes the agent's standing permanently |
| B4 | Constraint is elected, not imposed | orientation §IV | the profitable action remains available every round |
| B5 | The agent models a partner's future conduct | orientation §III | the partner is an agent, not a script |
| B6 | An inclusion decision about a partner's character | orientation §VI | the agent can admit or exclude, and partners differ |
| B7 | Joining time varies across arms | orientation §VI | at least one arm joins after the institution is established |

## Where this program stands against the checklist

`pledge_breach`, the instrument for EXP-045, is the program's most recent and
most controlled. Its `covenant` arm:

| Requirement | Status |
|---|---|
| A1 public pledge | met |
| A2 membership cost | met |
| B1 non-rivalrous good | **failed** — the reserve is money; 7 units contributed are 7 not kept |
| B2 no terminal value | **failed** — 17 rounds, a single claim at round 14, nothing at stake after it |
| B3 irreversible breach | **failed** — breaking the pledge costs nothing |
| B4 elected constraint | met |
| B5 partner modelled as an agent | **failed** — the partner is world state |
| B6 inclusion decision | **failed** — absent |
| B7 joining time varies | **failed** — every arm joins in round 1 |

So the arm satisfies Definition A completely and Definition B on one of seven
requirements. Every earlier instrument in this program — the warehouse
association, the trust game, `shared_reserve_commitment` — fails B1 and B2 in
the same way, because each organised cooperation around money over a finite
horizon.

**Consequence for how the program's null results are read.** The orientation
predicts defection pressure for rivalrous goods and attractive defection near a
terminal point. Five batches of flat institutional contrasts on rivalrous,
finite-horizon goods are therefore consistent with Definition B rather than
evidence against it. They are Definition B's control condition, run five times.
EXP-045 recorded the two predictions directly: 72 of 450 retentions in the
chosen-framing arms fell in the post-claim rounds where nothing remained at
stake, and 28 of 30 providers broke a pledge whose breach carried no cost.

**Consequence for sequencing.** Adding an enforcement mechanism — loss of
membership, forfeiture on breach — addresses B3 alone. Section II makes the
non-rivalrous infinite-horizon good the precondition for stability, so B1 and B2
come first; enforcement bolted onto a rivalrous finite good is predicted to fail
by the same argument that predicts the unenforced version fails. Any successor
instrument should establish B1 and B2 before a B3 ladder is built on it.

## One accidental alignment worth keeping

`pledge_breach` withholds the claim's size, timing, and the horizon, so the
provider affirms its pledge before it can calculate whether keeping it pays.
That is structurally *na'aseh v'nishma* — commitment preceding comprehension.
It was a side effect of removing computable sufficiency, not a deliberate
implementation of Section II, but it is the one place where the instrument's
information design matches the orientation rather than the paper.

## Rule going forward

Do not name an arm `covenant` without stating, in the experiment record's
`Design` section, which definition it implements and which checklist rows it
fails. The failure list is the interpretation: a result from an arm failing B1
and B2 cannot be reported as evidence about covenant in the orientation's sense,
in either direction.
