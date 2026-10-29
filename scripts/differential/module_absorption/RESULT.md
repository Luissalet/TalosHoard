# Last run (29 Oct 2026)

Oracle: each old repository at its last commit before the absorption, run as its own server from a `git archive` copy.
Probe: Talos with only that module on. Temporary data, fake capture/clipboard/network/process table, no real capture.

| Module | Old commit | Cases | `/api/agent/call` (Talos token) | `/<module>/api/agent/call` (module token) | Stability |
| --- | --- | --- | --- | --- | --- |
| Screen (Argus) | `869d46ea3bac57905f9f737f504db24d0b56a4ba` | 85 | pass, identical | pass, identical | 3 of 3 runs |
| Clipboard (Echo) | `cbfcb63c39fe2b44ffaed993b940f6490e8410ba` | 124 | pass, identical | pass, identical | 3 of 3 runs |
| Services (Cassandra) | `ed01cb042727c9b722cd033021c33dd7e83acb2a` | 148 | pass, identical | pass, identical | 3 of 3 runs |
| Disk (DiskHoard) | `acee94dfc1d7976f2d46b1b6c510f4204ca909e3` | 123 | pass, identical | pass, identical | 3 of 3 runs |

Negative control (`--mutate`): all eight harnesses fail, each at the case that exercises the broken behaviour.

| Module | Mutation | Failing case |
| --- | --- | --- |
| Screen | the day list loses its first day | `c000002`, `days[0].captured` expected 2, got 4 |
| Clipboard | `ClipStore.get` reports one extra character | `c000051`, `chars` expected 55, got 56 |
| Services | uptime percentage forced to -1 | `c000056`, `uptime_pct` expected 99.54, got -1.0 |
| Disk | size formatter returns "?" | `c000001`, `human` expected "72.5 MB", got "?" |

## What the runs showed

No divergence was found that was not already an intended difference: nothing was lost in the absorption, so no bug task was opened.
Every corpus holds real content (data written by the old code opened by Talos without conversion) and many error and not-found
cases. The intended differences (extra optional arguments, addresses of sibling apps, wording of wrapped errors) are listed in the
README of this folder and kept out of the comparison by the masks in `side.py`.
