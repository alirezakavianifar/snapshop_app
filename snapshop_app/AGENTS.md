# Agent Instructions

## Git Remote

Changes must be pushed to: **[g](https://github.com/alirezakavianifar/quran_mobile_app.git)[ithub.com/alirezakavianifar/snapshop_app.git](https://github.com/alirezakavianifar/snapshop_app.git)**

Ensure the remote `origin` points to this URL. If not configured, use: `git remote add origin https://github.com/alirezakavianifar/snapshop_app.git` or `git remote set-url origin <url>` to update).

## .gitignore

If `.gitignore` does not exist, create one based on the codebase structure and language. Adapt entries to match the project's technologies and build output locations.

## Git Push Workflow

When the user uses the keyword "push" in a request (e.g., "please push these changes", "push", or similar), you MUST follow this specific workflow:

1. **Stage all changes**: standard `git add .`
2. **Infer Commit Message**: Generate a concise, descriptive, and professional commit message based on the recent file changes and conversation context. Do not ask the user for a commit message unless they explicitly provide one.
3. **Commit**: `git commit -m "<inferred_message>"`
4. **Push to Git**: `git push` (or `git push -u origin <branch>` if the upstream is not set).
5. **Sync to Remote Windows Server**: Run `python sync_to_remote.py --full-sync` to sync all latest code changes to the remote Windows server (`94.184.36.117` at `C:\Users\Administrator\projects\snapshop_app\snapshop_app\snapshop_app`).

**Note:** You should proactively execute these commands without asking for extra confirmation if the user explicitly said "push".

## Language Rule

- Always respond and answer in English. Even if the user asks questions or provides input in another language (such as Persian), the agent must write all explanations, responses, and comments in English.

## README Requirement

- Always ensure the remote repository has an up-to-date `README.md` file that explains everything about the project, from how it is set up to how it is run. Include every single detail necessary so that if we were to run the project in the future, we can easily follow the steps in the README file and do exactly that.

## Implementation Planning

- Before coding, always create an implementation plan with a related name inside the [docs/](file:///e:/projects/domain/docs) folder.
- After completing each phase, run test cases to make sure everything is OK.
