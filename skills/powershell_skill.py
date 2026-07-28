"""
PowerShell Skill —— LLM 可调用的系统命令执行工具。
危险操作需用户确认。
"""
from skills.base import BaseSkill
import subprocess


class PowerShellSkill(BaseSkill):

    @property
    def name(self) -> str:
        return "powershell"

    def get_tools(self) -> list[dict]:
        return [
            {"name": "powershell_run", "fn": self.powershell_run,
             "schema": self._s("执行 PowerShell 命令并返回结果", {
                 "command": {"type": "string", "description": "PowerShell 命令"},
             }, ["command"])},
        ]

    def powershell_run(self, command: str) -> str:
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                capture_output=True, text=True, timeout=30, encoding="utf-8", errors="replace",
            )
            out = result.stdout.strip()[:2000]
            err = result.stderr.strip()[:500]
            if out and err:
                return f"{out}\n\n⚠️ 错误:\n{err}"
            elif out:
                return out
            elif err:
                return f"⚠️ {err}"
            elif result.returncode != 0:
                return f"❌ 命令返回代码: {result.returncode}"
            return "✅ 执行完成（无输出）"
        except subprocess.TimeoutExpired:
            return "❌ 命令超时（30秒）"
        except FileNotFoundError:
            return "❌ PowerShell 未找到"
        except Exception as e:
            return f"❌ 执行失败: {e}"

    @staticmethod
    def _s(desc, props, req=None):
        return {"type": "function", "function": {
            "description": desc, "parameters": {"type": "object", "properties": props, "required": req or []}}}
