# Receipt PR stack repair

The integration branch contained fixes that were absent from the owning PR branches. They are now present on those branches, and a fresh octopus merge reproduces the published integration's complete Git tree.

| Original change | Owning branch | Repair commit |
|---|---|---|
| Receipt/text and trace checks from `7b8c8181e` | `receipts-trace` / PR #1 | `335324430` |
| Registration, shared verifier and prover progress from `7b8c8181e` | `receipts-zk-poc` / PR #3 | `59a634c35` |
| UTF-8 fix `a75131993` | `receipts-trace` / PR #1 | `35461fad7` |
| Topology-policy README warning added only in merge `7bf600953` | `receipts-trace` / PR #1 | `3e7c0717e` |

The two parts of `7b8c8181e` were applied as path-restricted patches with the original commit identified in each commit message. The UTF-8 change was cherry-picked with its source reference. The dependent Lean and ZK branches merged the updated trace branch. No PR branch was rebased or force-pushed.

Validated branch heads:

- `receipts-trace`: `3e7c0717e`.
- `receipts-lean-spec`: `8554c8e21bb01cede3a09dacd5392264243aa5af`.
- `receipts-zk-poc`: `8e394bf6d4e7f2f6dd8671acc50f26a275fe9e31`.

A detached checkout of base `3057bb66c86c46d5781e50e85462a760ba7d1feb` merged these three branch heads using Git's octopus strategy, producing `0bf6078c81223074b162eb9c8a537c17a3adcb21`. Its tree is **`cb030dbda8feeac09fad9b81f2335b0b0fbf7185`**, identical to the old shipped revision `a751319930c824eb9cbb24a7c91c4a6ba18ac679`. The comparison covers every tracked file, including documentation, verifier code and circuit sources.

The first comparison caught the missing topology-policy warning. Moving that warning to the trace branch and repeating the fresh merge made the trees identical; no integration-only patch was used to repair the final merge.

The rebuilt merge was merged into the existing published integration history as **`e075aeb058c135e137dcf19ef9a63e761052e02a`**, also with the identical tree. The parent submodule pin and installer manifest now use this revision. This preserves existing commit references and makes every repaired PR branch reachable from `receipts-all`.

Validation: exact tree equality for the fresh branch merge and the published integration; portable API/setup/verifier tests; clean-tree benchmark guard tests covering staged, unstaged, untracked and submodule changes. Existing benchmark records retain their original revisions; the separate [provenance audit](../benchmarks/results/2026-09-13/provenance.json) explains what their saved digests establish.
