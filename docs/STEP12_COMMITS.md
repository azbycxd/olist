# Step 12 提交索引

Step12从Step11收尾22cb974之后开始，以下按Git时间顺序完整列出截至槽位协议2b8dcf1的全部提交（含失败测试、修复、协议及证据归档）。最后的第4批结果/文档归档提交包含本索引自身，其SHA在最终交付回复中列出；可用 `git log --reverse --format="%h %s" 22cb974..HEAD` 获得包含归档提交的完整列表。

| 提交 | 内容 |
| --- | --- |
| [cd24c60](https://github.com/azbycxd/olist/commit/cd24c604b3f66705fdb4e77eca09472af89f6ffc) | test(step12.1): reproduce retry and circuit breaker gaps |
| [44c6f14](https://github.com/azbycxd/olist/commit/44c6f143790695b8702767a30d8bcc87a18436d5) | fix(step12.1): classify retries and serialize provider circuits |
| [d4be752](https://github.com/azbycxd/olist/commit/d4be752a1ef8305e633b98030c6f6b2355e37a9c) | test(step12.1): reproduce alternating and empty-result loops |
| [f292108](https://github.com/azbycxd/olist/commit/f292108b74b1782ef904a3651362b58171a06f5c) | fix(step12.1): detect normalized repeated and empty tool loops |
| [5998c43](https://github.com/azbycxd/olist/commit/5998c43a6088612a4de264a473a3bab6159e792b) | test(step12.1): reproduce duplicate SQL after retries and recovery |
| [4dd9dab](https://github.com/azbycxd/olist/commit/4dd9dabe5cc346bae0a87f3ba172360266e7806a) | fix(step12.1): persist tool idempotency and deduplicate SQL execution |
| [4bd76cf](https://github.com/azbycxd/olist/commit/4bd76cf1b518fc3d48a410ae6e16938a3b934c1c) | test(step12.1): expose missing SQL truncation metadata |
| [d214e80](https://github.com/azbycxd/olist/commit/d214e806316e107e5d2c524d0226abbd2580d153) | fix(step12.1): persist and display explicit result truncation |
| [d6f725e](https://github.com/azbycxd/olist/commit/d6f725e7b932daf7f70e3a97b7f7ac5a197e0d2d) | docs(step12.1): record commit pairs and portable evidence checksums |
| [a8cf2ce](https://github.com/azbycxd/olist/commit/a8cf2ce7457beb7cf3d445c62657a28ca1ebfa8b) | test(step12.2): capture service gaps and SIGTERM recovery baseline |
| [76e5461](https://github.com/azbycxd/olist/commit/76e546109994d6a8fab31d00a5ece68d94f97b5b) | test(step12 review1): reproduce empty SQL results with fresh IDs |
| [df92eea](https://github.com/azbycxd/olist/commit/df92eea3e4aeb7e9f8b622a9670c37680b103c78) | fix(step12 review1): exclude zero-row IDs from evidence progress |
| [881e18e](https://github.com/azbycxd/olist/commit/881e18e8f2a27828421ec17a31eb9d54951854d0) | test(step12 review2): expose delayed failure events and circuit resets |
| [94bd518](https://github.com/azbycxd/olist/commit/94bd5189afae0a6adc1c650bff7960ef769ece4f) | fix(step12 review2): emit failures before backoff and preserve circuit counts |
| [48feb95](https://github.com/azbycxd/olist/commit/48feb95d96e651440e2072b33edbd0a6b82345a3) | fix(step12.2 B1): pool service connections and release worker leases gracefully |
| [684874d](https://github.com/azbycxd/olist/commit/684874df0136570ef708f5414947ab8a9e6b7e6b) | test(step12 review3): reproduce lost queued work during provider outages |
| [fa976f0](https://github.com/azbycxd/olist/commit/fa976f0cf269a1f20e954cfb45cba7e1d9fc69a3) | test(step12 review4): require public SQL to match the 1000 saved rows |
| [88746f1](https://github.com/azbycxd/olist/commit/88746f111f80592ed11434a8b733c1b878e4f86b) | fix(step12 review3): preserve queued and running work across provider outages |
| [b1ab325](https://github.com/azbycxd/olist/commit/b1ab32590f6b6df4119e3bb43c0e2157485acaf5) | fix(step12 review4): expose and hash capped SQL while probing one extra row |
| [1f84c33](https://github.com/azbycxd/olist/commit/1f84c33e236abc232faf617d25246ad4574d1759) | test(step12.2 B2): require shared provider buckets and inflight accounting |
| [2109e73](https://github.com/azbycxd/olist/commit/2109e73ae5302b1510972b8b17fe31f1bbb4e8b0) | test(step12.2 B2): reproduce extra memory call after rate timeout |
| [0c05250](https://github.com/azbycxd/olist/commit/0c052502dd5a9e177a5b5efe12bcdd52af4c4198) | fix(step12.2 B2): share provider rate buckets and reconcile token reservations |
| [84bfc75](https://github.com/azbycxd/olist/commit/84bfc7552a424bbd8abc91369c690a7055be44f5) | docs(step12): close batch one with commit map and evidence checksums |
| [d1bb2d2](https://github.com/azbycxd/olist/commit/d1bb2d21c1978c1df0b33060ae8582feecd02576) | test: reproduce explicit SQL limit truncation and cache collision |
| [914e315](https://github.com/azbycxd/olist/commit/914e315d91efa985eb8a8b3a962b43139723a993) | fix: preserve explicit limit semantics in probing and SQL deduplication |
| [9b87b73](https://github.com/azbycxd/olist/commit/9b87b73f75f00fcb69ee9017d418dce5f3cc9c32) | test: bound repeated provider fault requeues per task |
| [85861e2](https://github.com/azbycxd/olist/commit/85861e2001e254d7911be74947c88d6529130b9d) | fix: cap provider fault requeues at three per task |
| [770d61c](https://github.com/azbycxd/olist/commit/770d61c5ad3ec280cfd441ad08b97a1d4160fec7) | test: detect lost module docstrings in operational modules |
| [d651255](https://github.com/azbycxd/olist/commit/d651255442aa3cd2d1dddd9ffe606ce0a7a50620) | fix: restore operational module docstrings before imports |
| [57cccca](https://github.com/azbycxd/olist/commit/57cccca76c8293993f99879ec00114db69652b40) | test: reject token reservations larger than provider TPM capacity |
| [1f3333c](https://github.com/azbycxd/olist/commit/1f3333cbdb828d3185bd381ef6ff27b0fc259f64) | fix: fail oversized TPM reservations immediately with a reason |
| [fe20d11](https://github.com/azbycxd/olist/commit/fe20d1114afdd83ab04de2d8b92d1ec45dbb84d6) | test: require MCP readiness to verify the business reader database |
| [49ac00a](https://github.com/azbycxd/olist/commit/49ac00ac075897f889482e5963626614118d9e9a) | fix: check both MCP pools for readiness |
| [81ec99f](https://github.com/azbycxd/olist/commit/81ec99f7b904bb376b330dad0dd98f79030f273d) | test: require a short dedicated readiness acquisition timeout |
| [b495f70](https://github.com/azbycxd/olist/commit/b495f70376c48ab9457841333f5c06fba6c69a5a) | fix: use a dedicated one-second readiness connection timeout |
| [ecd397d](https://github.com/azbycxd/olist/commit/ecd397dca5dd891d4cb7b1e3ae8ab7a19cc7ec29) | docs: close all six batch-one review findings with test receipts |
| [f6a7e8e](https://github.com/azbycxd/olist/commit/f6a7e8ed53d9578c6ee5308748b29bd153dfeb55) | test: specify task trace propagation, GenAI spans and metrics |
| [4d8d7c8](https://github.com/azbycxd/olist/commit/4d8d7c89ca31ef9972d5c5f1c3113aa7ef1903f5) | feat: trace existing task execution and expose durable operational metrics |
| [82a2ab0](https://github.com/azbycxd/olist/commit/82a2ab039cbb3e534ae9354bd2d1df413928012a) | test: require measured chaos receipts and simultaneous SSE load |
| [9f3864a](https://github.com/azbycxd/olist/commit/9f3864af096128625744939cb65ea4f2b9c1928f) | test: complete measured database and network chaos plus 100-task SSE load |
| [9acf8a2](https://github.com/azbycxd/olist/commit/9acf8a2590275fc021712eefba18b71ae6093dc8) | docs: close Step 12.3 with commit pairs and archived evidence hashes |
| [2e77d1d](https://github.com/azbycxd/olist/commit/2e77d1d8ebce2235ef293b033baf03b86a84cc8e) | test: reproduce metric counter loss after retention and forbid event scans |
| [95e1529](https://github.com/azbycxd/olist/commit/95e1529d59d893ec2e52aeff233f4ebc1ef1ee70) | fix: persist retention-independent metrics in atomic event rollups |
| [0da3b45](https://github.com/azbycxd/olist/commit/0da3b45eeedc90cec096821f97c7e88212c2739e) | test: reproduce unrecoverable MCP outages and diagnose prior runtime failure |
| [ed959d4](https://github.com/azbycxd/olist/commit/ed959d4766e4aca841ad6dc8a759efba570965df) | fix: requeue transient MCP failures within the shared fault budget |
| [f33be49](https://github.com/azbycxd/olist/commit/f33be49ef022ac8264c8a22c386ac487a905f4b0) | test: reproduce timeout classification with the installed MCP SDK |
| [79d9c08](https://github.com/azbycxd/olist/commit/79d9c08f3eb7037cfcbd54dfcb1bebbaac34f0ff) | fix: classify actual MCP SDK request timeouts as recoverable infrastructure |
| [1516bb0](https://github.com/azbycxd/olist/commit/1516bb09a836af8653622ecf8d9bbd62c294293a) | test: require task JWT claims, role authorization and credential isolation |
| [8af577d](https://github.com/azbycxd/olist/commit/8af577df980b294bcac1f78b1cc870aa8e3a96b5) | fix(security): bind MCP access to task role and active lease |
| [a4e3fea](https://github.com/azbycxd/olist/commit/a4e3fea9b555ef907f7c8a3b1da13b4cf994ea87) | test(security): reproduce missing state scope and RLS enforcement |
| [ba87cc8](https://github.com/azbycxd/olist/commit/ba87cc81dfca8b7e1a50c9c137618d80454b04a7) | fix(security): enforce task user state scope with default-deny RLS |
| [3c10e94](https://github.com/azbycxd/olist/commit/3c10e946615fab5205949c1638f3a747c3a01577) | test(privacy): reproduce missing event redaction and retention maintenance |
| [733dbb0](https://github.com/azbycxd/olist/commit/733dbb06377a1cc99adbc5db0643291e6e10f765) | fix(privacy): redact events and add audited retention and user erasure |
| [39a303f](https://github.com/azbycxd/olist/commit/39a303f232400f9ced10bba2e4b7b22eb76c7aa2) | test(runtime): reproduce missing preflight context admission guard |
| [ccf447a](https://github.com/azbycxd/olist/commit/ccf447a817a501971bdee107d679b8dd569289fa) | fix(runtime): preflight context with observed conservative token estimate |
| [10f3064](https://github.com/azbycxd/olist/commit/10f306448a12bcd23ba5f3dbcca64a1218546347) | test(data): reproduce stale import versions and unsafe blackboard resume |
| [d91f713](https://github.com/azbycxd/olist/commit/d91f713fb6117b60d2105d483d8a488ec4458a60) | fix(data): invalidate stale findings and restart unknown blackboard versions |
| [b1105f2](https://github.com/azbycxd/olist/commit/b1105f2342d9f48bbb96131b7a80ef94b3ae5eb5) | test(runtime): reproduce missing fallback route on open provider circuit |
| [544e41c](https://github.com/azbycxd/olist/commit/544e41c1172db8bf263447129934c58ad8cd1dc1) | fix(runtime): route open primary circuits to configured fallback model |
| [8fd7034](https://github.com/azbycxd/olist/commit/8fd70340ba56edd4824d6c572dbb7e15d96743d0) | test(eval): require dev-only single-run regression marker |
| [d720be0](https://github.com/azbycxd/olist/commit/d720be08df946d8816a4a33101983ea7af2b5366) | fix(eval): enforce committed protocol and one-shot dev regression |
| [91f70b8](https://github.com/azbycxd/olist/commit/91f70b80a85ec991c53dab204dee108ced2ed2ba) | docs(eval): freeze Step12 single-run CDE dev regression protocol |
| [dfddee5](https://github.com/azbycxd/olist/commit/dfddee55a3d433a6e1d9b6e48fef645131b1249f) | test(eval): reproduce protocol verification in runtime images without git |
| [7728a59](https://github.com/azbycxd/olist/commit/7728a59ebd6f29a81f0c4996578a327424dda00b) | fix(eval): verify host commit ticket when runtime has no git |
| [17165f0](https://github.com/azbycxd/olist/commit/17165f0a4033ca39fe4b797800eddf7b0363afb4) | test(events): reproduce evaluator and MCP sequence collisions |
| [1d97b1e](https://github.com/azbycxd/olist/commit/1d97b1e1eb409aeef229aef25cac9dd27e32400e) | fix(events): serialize CLI evaluator and MCP event sequences transactionally |
| [c9eda85](https://github.com/azbycxd/olist/commit/c9eda85e54d3df8594c7523382e2b95e12eec64b) | test(build): detect missing privacy module in runtime image |
| [630a78d](https://github.com/azbycxd/olist/commit/630a78da124f78a4321130ca0b3d30c92677f2e4) | fix(build): include privacy module and verify packaged runtime |
| [c0c50a5](https://github.com/azbycxd/olist/commit/c0c50a5852fd2eedab16eaebb11fa08dfebb1c4e) | docs(step12): archive batch3 tests and aborted single-run regression |
| [81c0f5e](https://github.com/azbycxd/olist/commit/81c0f5e21c31664b4372cea938d7f575429447e3) | test(rls): diagnose nested policy costs and require transactional scope map |
| [2707572](https://github.com/azbycxd/olist/commit/2707572d532af4c51724bc06dc487c6677bbc5e2) | fix(rls): replace nested policies with transactional order scope map |
| [eeea24b](https://github.com/azbycxd/olist/commit/eeea24b36285dff77029dea3d31a68662c898f67) | docs(rls): archive one-pass optimization results and diagnosis |
| [6263ebd](https://github.com/azbycxd/olist/commit/6263ebd9bb4c71ca43a73d33009c929c07c281e0) | test(eval): require full HTTP rehearsal with concurrent SQL events |
| [294e1e8](https://github.com/azbycxd/olist/commit/294e1e83978703ee71cbfa8992c835098cad241c) | fix(eval): exercise complete evaluator using HTTP model rehearsal |
| [bffb81d](https://github.com/azbycxd/olist/commit/bffb81df8216a28e891ca8b2e948f38443ac5942) | test(eval): require v2 isolation and complete pricing before any model call |
| [91ac881](https://github.com/azbycxd/olist/commit/91ac881e9fefbb4295fda5b33723669963412d06) | test(eval): preserve clean container reproduction of v2 guard failures |
| [e98d609](https://github.com/azbycxd/olist/commit/e98d6093a00dce3300154c89ae02a1a4447f1f50) | fix(eval): isolate v2 artifacts and enforce pricing before startup |
| [203dd7f](https://github.com/azbycxd/olist/commit/203dd7f86bb42b074611ca53afebebf989ee6618) | docs(eval): freeze v2 protocol after successful full rehearsal |
| [7c90a58](https://github.com/azbycxd/olist/commit/7c90a58199274f5c5ba1876b17cb6e8e0c9b522a) | docs(step12): record RLS review and v2 waiting for required prices |
| [97b41df](https://github.com/azbycxd/olist/commit/97b41df484b7b36b6abcb540822780cd14f30ae4) | docs(eval): archive single v2 regression results and cost audit |
| [274ed0c](https://github.com/azbycxd/olist/commit/274ed0cc4a2e349ba7aabe861a9cba939ae6f201) | test(slots): reproduce missing resolution and pre-model clarification |
| [c39d3be](https://github.com/azbycxd/olist/commit/c39d3beda60fc181cd2f8c2ec4f8105b19ab7053) | feat(slots): resolve optional metric scope before model requests |
| [f46a05b](https://github.com/azbycxd/olist/commit/f46a05bf43ddb146db8a9d400f08356b5a7f21ce) | test(eval): require both slot rehearsal entrances and fixed adoption |
| [6d656a6](https://github.com/azbycxd/olist/commit/6d656a6478698a58778e0542af23f4dc62bae5b7) | feat(eval): add one-shot slot experiment with dual-entry rehearsal |
| [c4cc54b](https://github.com/azbycxd/olist/commit/c4cc54b9fcfb580bd8c09b63ac18540a762ee04a) | docs(step12): archive 41-case slot rehearsal and deferred designs |
| [2b8dcf1](https://github.com/azbycxd/olist/commit/2b8dcf1f0e198e7638e89e3858c03928d4e75592) | docs(eval): freeze one-shot slot adoption protocol after rehearsal |

第4批测试先行对照：C7失败274ed0c → 实现c39d3be；评估保护失败f46a05b → 实现6d656a6；替身证据c4cc54b → 独立协议2b8dcf1。结果出来后没有修改产品代码，不产生通过修改算法来重测的提交。

各历史子项的红/绿对照和对应XML见[HARDENING_HISTORY](STEP12_HARDENING_HISTORY.md)，实际最终行为与局限以[HARDENING](STEP12_HARDENING.md)为准。
