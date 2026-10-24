# 手动卸载

一般用 `token-stats uninstall` 卸载（v0.1.1 起提供，更早的版本先重新运行安装命令升级）。程序已经删除、只剩定时任务等情况，按下面的步骤手动处理。

1. 移除定时任务（没装可以跳过）：

   ```bash
   # macOS
   launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.token-stats.sync.plist
   rm ~/Library/LaunchAgents/com.token-stats.sync.plist

   # Linux（systemd）
   systemctl --user disable --now token-stats.timer
   rm ~/.config/systemd/user/token-stats.service ~/.config/systemd/user/token-stats.timer
   systemctl --user daemon-reload

   # Linux（crontab）
   crontab -l | grep -v '# token-stats sync$' | crontab -
   ```

   ```powershell
   # Windows
   schtasks /Delete /TN token-stats /F
   ```

2. 删除程序和启动脚本：

   ```bash
   rm -rf ~/.local/share/token-stats/app ~/.local/bin/token-stats
   ```

   ```powershell
   Remove-Item -Recurse "$env:LOCALAPPDATA\token-stats\app", "$env:LOCALAPPDATA\token-stats\bin"
   ```

3. 配置和数据是否删除由你决定。**usage.db 中保存着全部历史，其中超过 30 天的 Claude Code 记录在日志中已经不存在，删除后无法恢复。** 要彻底删除：macOS / Linux 删除 `~/.config/token-stats` 和 `~/.local/share/token-stats`；Windows 删除 `%APPDATA%\token-stats` 和 `%LOCALAPPDATA%\token-stats`。发布仓库在 GitHub 上，需要自己删除。
