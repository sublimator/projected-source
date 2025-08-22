"""
GitHub integration for permalinks and git blame.
Adapted from rwdb-online-delete-fix.py
"""

import datetime
import logging
import re
import subprocess
from pathlib import Path
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class GitHubIntegration:
    """Handle GitHub permalinks and git operations."""
    
    def __init__(self, repo_path: Path = None):
        self.repo_path = repo_path or Path.cwd()
        self._github_url = None
        self._commit_hash = None
        self._initialized = False
    
    def _init_repo_info(self):
        """Lazy initialization of repository information."""
        if self._initialized:
            return
        
        try:
            # Get the remote origin URL
            origin_url = subprocess.check_output(
                ['git', 'remote', 'get-url', 'origin'],
                cwd=self.repo_path,
                stderr=subprocess.DEVNULL
            ).decode().strip()
            
            # Get current commit hash
            self._commit_hash = subprocess.check_output(
                ['git', 'rev-parse', 'HEAD'],
                cwd=self.repo_path,
                stderr=subprocess.DEVNULL
            ).decode().strip()
            
            # Convert SSH/HTTPS URL to GitHub web URL
            if origin_url.startswith('git@github.com:'):
                # SSH format: git@github.com:user/repo.git
                repo_path = origin_url.replace('git@github.com:', '').replace('.git', '')
            elif 'github.com' in origin_url:
                # HTTPS format: https://github.com/user/repo.git
                repo_path = re.sub(r'https?://github\.com/', '', origin_url).replace('.git', '')
            else:
                logger.warning(f"Non-GitHub repository: {origin_url}")
                self._initialized = True
                return
            
            self._github_url = f"https://github.com/{repo_path}"
            logger.debug(f"GitHub URL: {self._github_url}, Commit: {self._commit_hash[:8]}")
            
        except subprocess.CalledProcessError as e:
            logger.warning(f"Git command failed: {e}")
        except Exception as e:
            logger.warning(f"Failed to get GitHub info: {e}")
        
        self._initialized = True
    
    @property
    def github_url(self) -> Optional[str]:
        """Get the GitHub repository URL."""
        self._init_repo_info()
        return self._github_url
    
    @property
    def commit_hash(self) -> Optional[str]:
        """Get the current commit hash."""
        self._init_repo_info()
        return self._commit_hash
    
    def get_permalink(self, file_path: Path, start_line: int = None, end_line: int = None) -> str:
        """
        Generate a GitHub permalink for a file or line range.
        
        Args:
            file_path: Path to the file
            start_line: Optional start line number (1-based)
            end_line: Optional end line number (1-based)
            
        Returns:
            Formatted markdown link or plain text reference
        """
        # Make path relative to repo root
        try:
            if file_path.is_absolute():
                rel_path = file_path.relative_to(self.repo_path)
            else:
                rel_path = file_path
        except ValueError:
            rel_path = file_path
        
        if self.github_url and self.commit_hash:
            # Build GitHub URL
            url = f"{self.github_url}/blob/{self.commit_hash}/{rel_path}"
            
            # Add line anchors if specified
            if start_line is not None:
                if end_line and end_line != start_line:
                    url += f"#L{start_line}-L{end_line}"
                    display = f"{rel_path}:{start_line}-{end_line}"
                else:
                    url += f"#L{start_line}"
                    display = f"{rel_path}:{start_line}"
            else:
                display = str(rel_path)
            
            # Return as markdown link
            return f"📍 [`{display}`]({url})"
        else:
            # No GitHub info, return plain text
            if start_line is not None:
                if end_line and end_line != start_line:
                    return f"📍 `{rel_path}:{start_line}-{end_line}`"
                else:
                    return f"📍 `{rel_path}:{start_line}`"
            else:
                return f"📍 `{rel_path}`"
    
    def get_blame(self, file_path: Path, start_line: int, end_line: int) -> Dict[int, Dict]:
        """
        Get git blame information for a line range.
        
        Args:
            file_path: Path to the file
            start_line: Start line number (1-based)
            end_line: End line number (1-based)
            
        Returns:
            Dict mapping line numbers to blame info
        """
        try:
            blame_output = subprocess.check_output([
                'git', 'blame', '-L', f'{start_line},{end_line}',
                '--porcelain', str(file_path)
            ], cwd=self.repo_path, stderr=subprocess.DEVNULL).decode()
            
            blame_info = {}
            lines = blame_output.split('\n')
            i = 0
            
            while i < len(lines):
                line = lines[i]
                if line and not line.startswith('\t'):
                    parts = line.split(' ')
                    if len(parts) >= 3:
                        commit_hash = parts[0]
                        original_line = int(parts[1])
                        final_line = int(parts[2])
                        
                        # Extract commit metadata
                        author = ""
                        date = ""
                        i += 1
                        
                        while i < len(lines) and not lines[i].startswith('\t'):
                            if lines[i].startswith('author '):
                                author = lines[i][7:]
                            elif lines[i].startswith('author-time '):
                                timestamp = int(lines[i][12:])
                                date = datetime.datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d')
                            i += 1
                        
                        blame_info[final_line] = {
                            'commit': commit_hash[:8],
                            'author': author[:20],  # Truncate long names
                            'date': date
                        }
                i += 1
            
            return blame_info
            
        except subprocess.CalledProcessError as e:
            logger.warning(f"Git blame failed: {e}")
            return {}
        except Exception as e:
            logger.error(f"Error getting blame info: {e}")
            return {}
    
    def format_with_blame(self, code_text: str, start_line: int, file_path: Path) -> str:
        """
        Format code with git blame information.
        
        Args:
            code_text: The code to format
            start_line: Starting line number
            file_path: Path to the file
            
        Returns:
            Formatted code with blame info
        """
        lines = code_text.splitlines()
        end_line = start_line + len(lines) - 1
        
        blame_info = self.get_blame(file_path, start_line, end_line)
        
        formatted_lines = []
        for i, line in enumerate(lines):
            line_num = start_line + i
            
            if line_num in blame_info:
                blame = blame_info[line_num]
                # Format: line_num | commit | author | date | code
                formatted_line = (
                    f"{line_num:4} │ {blame['commit']} │ "
                    f"{blame['author']:<20} │ {blame['date']} │ {line}"
                )
            else:
                formatted_line = f"{line_num:4} │ {line}"
            
            formatted_lines.append(formatted_line)
        
        return '\n'.join(formatted_lines)