# Git 分支合并指南

## 分支结构

| 分支 | 用途 |
| --- | --- |
| `main` | 网站功能开发（新功能、bug 修复、前端/后端改动） |
| `feature/nginx-reverse-proxy` | 网站部署（Nginx 反向代理配置、部署脚本、部署相关文档） |

两个分支的关系：

```
main:  A → B → C → D → E  （功能提交）
           ↘
feature:    F  （部署相关提交：nginx 配置 + 部署文档）
```

`feature/nginx-reverse-proxy` 包含 main 的所有功能代码，在此基础上叠加了 Nginx 部署配置。

## 合并场景

当 main 分支有新的功能更新后，需要将这些更新同步到部署分支，以便部署最新版本的网站。

## 操作步骤

### 1. 确保本地 main 是最新的

```bash
git checkout main
git pull origin main
```

### 2. 切换到部署分支

```bash
git checkout feature/nginx-reverse-proxy
```

### 3. 将 main 合并到当前分支

```bash
git merge main
```

这一步会将 main 上所有新增的功能提交合并到部署分支。

### 4. 处理可能的冲突（重点）

合并时，Git 对每个文件的处理分两种情况：**自动合并**和**手动解决**。理解这两者的区别是关键。

#### 4.1 Git 如何判断能否自动合并？

Git 使用"三路合并"（three-way merge）算法，依赖三个版本：

```
共同祖先（base）── 文件在分叉前的原始内容
    ├── main 版本（ours）  ── main 上的最新内容
    └── 部署分支版本（theirs）── 本分支的最新内容
```

**Git 能自动合并的情况**：两个分支修改了文件的不同区域（不同行），互不重叠。Git 直接将双方改动叠加在一起，无需人工干预。

**Git 无法自动合并的情况**：两个分支修改了同一文件的同一行（或相邻行），Git 无法判断以谁为准，此时发生冲突（conflict），必须人工决定。

#### 4.2 本项目的冲突风险分析

当前两个分支的差异是：

- 部署分支比 main 多出 4 个文件：`DEBUG.md`（新增 nginx 节）、`nginx_config/GUIDE.md`、`nginx_config/nginx-stock.conf`、`nginx_config/setup_nginx.sh`
- `nginx_config/` 下的 3 个文件是部署分支独有的，main 不会修改它们，**合并时永不冲突**
- `DEBUG.md` 两个分支都有，是冲突的唯一风险点

具体场景：

| main 的改动 | 部署分支的改动 | 结果 |
| --- | --- | --- |
| 修改后端代码、前端页面等 | 无改动 | Git 自动合并，无冲突 |
| 修改 `README.md` 中间部分 | 无改动 | Git 自动合并，无冲突 |
| 在 `DEBUG.md` 末尾追加新内容 | 在 `DEBUG.md` 末尾追加了 nginx 节 | **冲突**，同一区域被双方修改 |

#### 4.3 实际操作：判断是否需要手动处理

执行 `git merge main` 后，Git 会立即告诉你结果：

```bash
$ git merge main

Auto-merging README.md           # Git 自动处理了 README
Auto-merging DEBUG.md            # Git 尝试处理 DEBUG.md
CONFLICT (content): Merge conflict in DEBUG.md   # 失败了，需要手动处理
Automatic merge failed; fix conflicts and then commit the result.
```

- 看到 `Auto-merging ...`— Git 已自动完成，无需你做任何事
- 看到 `CONFLICT ...`— 必须手动处理

大多数情况下合并会完全自动完成（`Already up to date` 或没有任何 CONFLICT 行），你只需继续 push。只有当输出中出现 `CONFLICT` 字样时才需要手动干预。

#### 4.4 手动解决冲突：以 DEBUG.md 为例

假设场景：main 在 `DEBUG.md` 末尾追加了一条新调试记录，部署分支之前也在末尾追加了 nginx 节。Git 发现同一区域被双方修改，无法自动合并。

**Step 1：查看冲突文件内容**

打开 `DEBUG.md`，Git 已经在文件中插入了冲突标记：

```
## 聊天 API 需要 ANTHROPIC_API_KEY

...原有共同内容...

---

<<<<<<< HEAD                          ← 当前分支（部署分支）的内容开始
## Nginx 403 权限及 Header 透传注意事项  ← 部署分支新增的 nginx 节

...nginx 相关记录...
=======                               ← 分隔线
## 新功能的调试记录                     ← main 分支新增的内容

...main 新增的调试记录...
>>>>>>> main                          ← main 分支的内容结束
```

**Step 2：手动编辑，保留双方内容**

把冲突标记删掉，将双方内容都保留下来：

```
## 聊天 API 需要 ANTHROPIC_API_KEY

...原有共同内容...

---

## Nginx 403 权限及 Header 透传注意事项

...nginx 相关记录...

---

## 新功能的调试记录

...main 新增的调试记录...
```

核心原则：**冲突标记是 Git 留给你的选择题，你的任务是把双方内容合并到一起，然后删掉标记。**

**Step 3：标记为已解决**

```bash
git add DEBUG.md
```

**Step 4：完成合并**

```bash
git commit
```

Git 会自动生成一个合并提交信息，直接保存退出即可。也可以写成自定义信息：

```bash
git commit -m "Merge main: 同步功能更新"
```

#### 4.5 冲突解决原则

- **README.md**：保留双方内容。部署分支中关于 Nginx 配置、部署步骤的部分应与 main 中的功能说明合并。
- **DEBUG.md**：保留双方内容。main 中的调试记录和部署分支中的 Nginx 相关记录都应保留。
- **`nginx_config/` 目录**：部署分支独有，合并时不受影响，永无冲突。
- **其他后端/前端文件**：部署分支不会修改它们，由 Git 自动合并，无需处理。

#### 4.6 快速判断：合并是否有冲突？

执行合并前可以先预览冲突情况：

```bash
# 在合并前检查哪些文件会有冲突（不实际执行合并）
git merge main --no-commit --no-ff
git diff --name-only --diff-filter=U    # 列出所有冲突文件
git merge --abort                        # 取消本次合并，回到合并前状态
```

### 5. 验证合并结果

```bash
# 确认部署文件完整
ls nginx_config/

# 确认新功能代码已合入
git log --oneline -5

# 运行测试（如果有）
python -m pytest
```

### 6. 推送到远程

```bash
git push origin feature/nginx-reverse-proxy
```

## 完整流程速查

```bash
git checkout main
git pull origin main
git checkout feature/nginx-reverse-proxy
git merge main
# 解决冲突（如有）
# git add . && git commit
git push origin feature/nginx-reverse-proxy
```

## 常见问题

### Q: 为什么不用 rebase？

部署分支已经推送到远程（`origin/feature/nginx-reverse-proxy`），rebase 会改写提交历史，需要 force push，风险较高。使用 merge 保留完整历史，更安全。

### Q: 如果冲突很多怎么办？

如果某次合并涉及的改动过大，可以分步进行：

```bash
# 先查看 main 上新增了哪些提交
git log feature/nginx-reverse-proxy..main --oneline

# 逐个 cherry-pick 关键提交，减少一次性冲突量
git cherry-pick <commit-hash>
```

### Q: 如何回滚一次错误的合并？

```bash
# 查看合并前的提交
git reflog

# 回退到合并前的状态
git reset --hard <合并前的commit>
```
