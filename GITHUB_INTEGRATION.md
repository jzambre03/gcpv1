# GitHub Integration Guide

## Overview

The application has been successfully updated to support **both GitHub and GitLab** repositories. The system automatically detects which platform you're using based on the repository URL and uses the appropriate API and authentication method.

## What Changed

### 1. **Git Authentication (`shared/git_operations.py`)**
- Updated `setup_git_auth()` function to automatically detect GitHub vs GitLab
- GitHub authentication: `https://TOKEN@github.com/...`
- GitLab authentication: `https://oauth2:TOKEN@gitlab.com/...`
- Falls back gracefully if platform can't be detected

### 2. **VSAT Sync Script (`scripts/vsat_sync.py`)**
- Added `fetch_github_repos()` function to fetch repositories from GitHub API
- Added `check_main_branch_parallel_github()` for GitHub branch validation
- Updated `fetch_vsat_projects()` to auto-detect GitHub vs GitLab
- Normalizes GitHub API responses to match GitLab structure for compatibility
- Added rate limit handling for GitHub API (5000 requests/hour with token)

### 3. **Config Collector Agent (`Agents/workers/config_collector/config_collector_agent.py`)**
- Added `get_git_token()` helper function to select correct token based on URL
- Updated all Git operations to use appropriate token (GitHub or GitLab)

### 4. **Configuration Files**
- `.env` - Separated `GITHUB_TOKEN` and `GITLAB_TOKEN`
- `env.example` - Added documentation for both tokens
- `config/vsat_master.yaml` - Updated comments to show GitHub support
- `README.md` - Updated documentation to reflect dual platform support

### 5. **Shared Config (`shared/config.py`)**
- Already had `GITHUB_TOKEN` support in the Config class
- No changes needed (was already prepared for GitHub!)

## How to Use

### 1. Set Up GitHub Token

Generate a GitHub Personal Access Token:
1. Go to https://github.com/settings/tokens
2. Click "Generate new token" (classic)
3. Select scopes:
   - ✅ `repo` (Full control of private repositories)
4. Copy the token

Add it to your `.env` file:
```bash
GITHUB_TOKEN=github_pat_YOUR_TOKEN_HERE
```

### 2. Configure VSAT for GitHub

In `config/vsat_master.yaml`:

```yaml
vsats:
  - name: jayeshics              # GitHub username or org name
    url: https://github.com/jayeshics
    enabled: true
```

### 3. Run VSAT Sync

```bash
python scripts/vsat_sync.py
```

The system will:
1. ✅ Detect it's a GitHub URL
2. ✅ Use GitHub API to fetch repositories
3. ✅ Filter repositories (only those with `main` branch by default)
4. ✅ Add repositories to database
5. ✅ Create golden branches for each repository

## Mixing GitHub and GitLab

You can have both GitHub and GitLab VSATs in the same config:

```yaml
vsats:
  # GitHub VSAT
  - name: jayeshics
    url: https://github.com/jayeshics
    enabled: true
  
  # GitLab VSAT
  - name: company_team
    url: https://gitlab.company.com/company_team
    enabled: true
```

Just make sure both tokens are set in `.env`:
```bash
GITHUB_TOKEN=github_pat_...
GITLAB_TOKEN=glpat-...
```

## API Differences Handled

### GitHub API
- Endpoint: `https://api.github.com/users/{username}/repos`
- Alternative: `https://api.github.com/orgs/{org}/repos`
- Auth: `Authorization: token {TOKEN}`
- Rate limit: 5000 requests/hour (with token)

### GitLab API
- Endpoint: `https://gitlab.com/api/v4/groups/{group}/projects`
- Alternative: `https://gitlab.com/api/v4/users/{user}/projects`
- Auth: `PRIVATE-TOKEN: {TOKEN}`
- Rate limit: Varies by GitLab instance

### Auto-Detection Logic
```python
if 'github.com' in url.lower():
    # Use GitHub API
    fetch_github_repos(...)
else:
    # Use GitLab API
    fetch_gitlab_projects(...)
```

## GitHub API Features

### Repository Filtering
- ✅ Skips archived repositories
- ✅ Checks for `main` branch (parallel execution, 50 concurrent checks)
- ✅ Supports both user and organization repositories

### Error Handling
- ✅ Authentication failures (401)
- ✅ Rate limit detection (403 with rate limit headers)
- ✅ Not found errors (404)
- ✅ Automatic retry with exponential backoff

### Response Normalization
GitHub responses are normalized to match GitLab structure:
```python
{
    'id': repo['id'],
    'name': repo['name'],
    'path': repo['name'],
    'http_url_to_repo': repo['clone_url'],
    'web_url': repo['html_url'],
    'description': repo['description'],
    'default_branch': repo['default_branch']
}
```

## Troubleshooting

### "GitHub URL detected but GITHUB_TOKEN not set"
**Solution**: Add `GITHUB_TOKEN` to your `.env` file

### "Authentication failed for GitHub user/org"
**Solution**: Check that your token is valid and hasn't expired

### "GitHub API rate limit exceeded"
**Solution**: Wait for rate limit reset or use a token with higher limits

### "User/org not found"
**Solution**: Verify the username/org name in `config/vsat_master.yaml`

### Repository not being fetched
**Possible causes**:
1. Repository is archived (automatically skipped)
2. Repository doesn't have a `main` branch (filtered out by default)
3. Repository is private and token doesn't have access

**To fetch repos without main branch**:
Set `require_main_branch: false` in `config/vsat_config.yaml`:
```yaml
filters:
  require_main_branch: false
```

## Testing

To test GitHub integration:

```bash
# Test VSAT sync
python scripts/vsat_sync.py

# Check logs
tail -f logs/vsat_sync/jayeshics_*/sync.log

# Verify services in database
sqlite3 config_data/golden_config.db "SELECT service_id, service_name FROM services WHERE vsat='jayeshics';"
```

## Benefits

✅ **Unified Interface**: Same codebase works with both platforms
✅ **Automatic Detection**: No manual configuration of platform type
✅ **Parallel Processing**: 50 concurrent branch checks for speed
✅ **Error Resilience**: Comprehensive error handling and retries
✅ **Cost Efficient**: Batch API calls and smart filtering
✅ **Future Proof**: Easy to add more Git platforms (Bitbucket, etc.)

## Next Steps

1. ✅ GitHub integration is complete
2. ✅ VSAT sync can fetch GitHub repos
3. ✅ Git operations work with GitHub
4. ✅ Config collector agent supports GitHub

You can now:
- Add GitHub VSATs to `config/vsat_master.yaml`
- Run VSAT sync to discover repositories
- Create golden branches for GitHub repos
- Perform drift detection on GitHub repositories

All existing functionality (drift detection, policy validation, AI analysis) works seamlessly with GitHub repositories!
