## 任务
帮我提交代码、推送并创建 PR，开启 auto-merge（squash）

## 上下文（自动收集）
当前 git 状态：
$( git status )

最近的改动：
$( git diff --stat )

当前分支：
$( git branch --show-current )

## 执行步骤
1. 如果没有改动或当前在 main/master 分支，停止并告知用户
2. 根据改动写一个 conventional commit message
3. git add . && git commit && git push
4. 创建 PR，标题和描述基于改动内容自动生成
5. 开启 auto-merge：gh pr merge --auto --squash
6. 输出 PR 链接，确认 auto-merge 已开启