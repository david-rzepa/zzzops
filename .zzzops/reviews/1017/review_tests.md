# review_tests G1017 (attempt 2): approved

review_tests:1:1 resolved: sentinel terms verified absent from rev 6.3 (SPEC/DESIGN/PLAN) and stable against G1022/G1024/G1025 designs (they keep filter_design and shrink). review_tests:1:2 resolved: pending-or-logged (not both) test for G1022/G1024/G1025 stays green after landing. Non-blocking: in_history matches any section 4 table line naming the goal, so unrelated rows naming G1022/G1024/G1025 would trip the not-both check.
