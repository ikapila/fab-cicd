# Azure DevOps Build Service Permissions Fix

## ✅ RECOMMENDED SOLUTION: Enable OAuth Token Access

The pipeline now uses `System.AccessToken` for authentication, which is simpler and more reliable.

### Required Setting (One-Time Setup):

1. **Open Pipeline Settings**
   - Go to your pipeline in Azure DevOps
   - Click **Edit** (top right)
   - Click the **⋮** (three dots) menu → **Triggers**
   - Or go to: `https://dev.azure.com/Arbuthnot-AAG/AAG-Proj-DataFabric/_build?definitionId=<YOUR_PIPELINE_ID>`

2. **Enable OAuth Token**
   - Go to **YAML** tab (if you were in Triggers)
   - Click **⋮** (three dots) → **Settings** 
   - Or navigate to the pipeline and select **More actions** → **Settings**
   - Under **Advanced settings** or in the settings page
   - Enable: **"Allow scripts to access the OAuth token"**
   - Save

   Alternative path:
   - Pipeline → **Edit** → **⋮ More Actions** → **Pipeline settings**
   - Check: ☑ **Allow scripts to access the OAuth token**

3. **Run Pipeline**
   - The System.AccessToken will automatically have push permissions
   - No manual permission grants needed

---

## Alternative: Manual Permissions (If OAuth Doesn't Work)

If enabling OAuth token doesn't work or is blocked by policy, use manual permissions:

## Problem
The build pipeline fails to push deployment tracking files with error:
```
TF401027: You need the Git 'GenericContribute' permission to perform this action.
fatal: unable to access '...': The requested URL returned error: 403
```

## Root Cause
The build service account (`Build\<guid>`) doesn't have permission to push commits back to the repository.

## Solution

### Step 1: Grant Repository Permissions

1. **Navigate to Project Settings**
   - Go to your Azure DevOps project
   - Click on **Project Settings** (bottom left corner)

2. **Open Repository Security**
   - Go to **Repos** → **Repositories**
   - Select your repository (e.g., `AAG-Proj-Sandbox`)
   - Click on the **Security** tab

3. **Add Build Service Account**
   - Click **+ Add**
   - Search for: `<Project Name> Build Service (<Organization Name>)`
   - Example: `AAG-Proj-DataFabric Build Service (Arbuthnot-AAG)`

4. **Grant Contribute Permission**
   - In the permissions list, find **Contribute**
   - Set it to **Allow** (green checkmark)
   
   Optional: Also set these to **Allow**:
   - **Create branch** - Allow
   - **Create tag** - Allow (if needed)

### Step 2: Alternative - Use Project-Level Build Service

If the above doesn't work, try adding the project collection build service:

1. In Repository Security, click **+ Add**
2. Search for: `Project Collection Build Service (<Organization Name>)`
3. Grant **Contribute** permission

### Step 3: Verify in Your Case

Based on your error message, you need to grant permissions to:
- **Identity**: `Build\7f9a65c9-21e6-49ed-838b-b36f25b3266a`
- **Repository**: `AAG-Proj-Sandbox` in `AAG-Proj-DataFabric` project
- **Organization**: `Arbuthnot-AAG`

**Exact steps for your setup:**
1. Go to: https://dev.azure.com/Arbuthnot-AAG/AAG-Proj-DataFabric/_settings/repositories
2. Select repository: `AAG-Proj-Sandbox`
3. Click **Security** tab
4. Add: `AAG-Proj-DataFabric Build Service (Arbuthnot-AAG)`
5. Set **Contribute** = **Allow**

### Step 4: Alternative Approach - Bypass Policy (Not Recommended)

If you have branch policies enabled on `dev`, `uat`, or `main` branches:

1. Go to **Project Settings** → **Repos** → **Repositories** → **Your Repo**
2. Click **Policies** tab
3. Select the branch (e.g., `dev`)
4. Under **Bypass policies when completing pull requests**:
   - Add the Build Service account
   - Grant **Bypass policies when pushing**

⚠️ **Note**: This is less secure and not recommended for production branches.

## Testing

After granting permissions:

1. Run the pipeline again
2. Check the "Update deployment tracking" step output
3. You should see:
   ```
   Pushing to remote branch: dev...
   ✓ Deployment tracking updated and pushed
   ```

4. Verify the file exists in the repo:
   - Navigate to `.deployment_tracking/dev_last_commit.txt` in Azure Repos
   - File should contain the commit hash and timestamp

## Troubleshooting

### Still Getting 403 Error?

1. **Check if PAT is required**: Some organizations require Personal Access Tokens
   - Create a PAT with `Code (Read & Write)` permission
   - Add it as a pipeline variable: `SYSTEM_ACCESSTOKEN`
   - Update checkout step to use PAT

2. **Check organization policies**: Your organization may have additional security policies

3. **Check branch policies**: Branch may require pull requests instead of direct pushes

### Best Practice Alternative

If direct push permissions are blocked by policy, consider:

1. **Use Git Tags instead of files**: Tag commits instead of tracking files
2. **Use Pipeline Variables**: Store last deployment in Azure DevOps variables
3. **Use Azure Storage**: Store tracking state in Azure Storage account
4. **Always deploy all**: Use `--force-all` flag to deploy all artifacts every time

## Next Steps

Once permissions are granted, commit the updated `azure-pipelines.yml` which includes:
- ✅ Fixed branch reference (`SourceBranchName` instead of `SourceBranch`)
- ✅ Better error handling and debugging
- ✅ Proper change detection on subsequent deployments
