这个后端项目使用python开发，环境管理器使用uv

开发前记得初始化git环境，包括 .gitignore 的东西也要弄上

每次开发完毕之后，记得提交 git commit 

每次开发都需要你完善而且完整，可以多测试，和多方面更好的设计，开发时间长，开发的东西多都是ok的，

本地测试的话数据库就先使用 sqlite, 这些东西后期需要可以通过.env 来修改，后面可能会改用 PostgreSQL


## 其他注意事项

### 版本控制 (Git & Versioning)
- **版本号规则 (Semantic Versioning)**:
  - 遵循 `Major.Minor.Patch` (主版本.次版本.修订号)。
  - **当前阶段**: 严格保持主版本号为 `0` (如 0.0.1, 0.1.2)，直到我明确指令发布 "v1.0.0"。
  - **版本递增逻辑**:
    - 小修复/Bug Fix -> 增加 Patch (如 0.0.1 -> 0.0.2)。
    - plan新增 (用户追加了很多东西,或者开发了新的功能) -> 增加 Minor (如 0.0.1 -> 0.1.0)。
      - 如果是0.1 这样的变更，那么 git commit 信息应该完整包含 新的功能和修复bug等等详细东西
- **提交信息 (Git Commit)**:
  - 每次代码交付后，请在末尾提供一个标准的 Git Commit Message(中文优先)，然后将这次改动的修改的代码提交git
  - 格式遵循 **Conventional Commits** (例如: `feat: add user login`, `fix: database connection`).
  - **变更日志**: 如果是 Minor 版本变动，请附带一段详细的 Changelog。


