/**
 * Courtroom Chronicles: copy new episode JSON files from Drive to GitHub.
 *
 * Add this file to your Apps Script project (script.google.com).
 *
 * One-time setup: Project Settings > Script properties
 *   GH_TOKEN  fine-grained GitHub token, this one repo only, permission "Contents: Read and write"
 *   GH_REPO   your-username/your-repo-name
 * Optional:
 *   GH_BRANCH           defaults to main
 *   EPISODES_FOLDER_ID  defaults to your EPISODES folder
 *
 * Use: run publishNewEpisodes() once by hand (approve the permissions), then add a
 * time-driven trigger (Triggers > Add trigger > publishNewEpisodes > Day timer).
 *
 * It looks one level down in the EPISODES folder for files named ep001.json, ep012.json ...
 * Unchanged files are skipped, so running it again is safe. Each file it adds or changes
 * triggers the GitHub Action, which rebuilds the site.
 */

function cfg() {
  var p = PropertiesService.getScriptProperties();
  var c = {
    token: p.getProperty('GH_TOKEN'),
    repo: p.getProperty('GH_REPO'),
    branch: p.getProperty('GH_BRANCH') || 'main',
    folder: p.getProperty('EPISODES_FOLDER_ID') || '1S0LHDEZT1PR8rNx53W92PdKo3zuVkZSb'
  };
  if (!c.token || !c.repo) throw new Error('Set GH_TOKEN and GH_REPO in Script properties');
  // Accept "https://github.com/user/repo", "user/repo.git" and stray spaces.
  c.repo = c.repo.trim().replace(/^https?:\/\/github\.com\//i, '').replace(/\.git$/i, '').replace(/\/+$/, '');
  c.token = c.token.trim();
  return c;
}

/** Run this first if publishing fails. It says exactly what is wrong. */
function checkGitHub() {
  var msg = checkAccess_(cfg());
  Logger.log(msg);
  return msg;
}

function checkAccess_(c) {
  var h = { Authorization: 'Bearer ' + c.token, Accept: 'application/vnd.github+json' };
  var r = UrlFetchApp.fetch('https://api.github.com/repos/' + c.repo, { headers: h, muteHttpExceptions: true });
  var code = r.getResponseCode();
  if (code === 401) return 'ERROR: GitHub rejected the token (401). It is wrong, expired or revoked. Make a new one and update GH_TOKEN.';
  if (code === 404) return 'ERROR: repo "' + c.repo + '" not found for this token (404). Either GH_REPO is misspelled (it must look like username/repo-name), or the token was not given access to this repo (token settings > Repository access > select this repo).';
  if (code !== 200) return 'ERROR: GitHub returned ' + code + ': ' + r.getContentText();
  var info = JSON.parse(r.getContentText());
  if (info.permissions && info.permissions.push === false) return 'ERROR: token can read "' + c.repo + '" but cannot write. Give it Contents: Read and write.';
  var b = UrlFetchApp.fetch('https://api.github.com/repos/' + c.repo + '/branches/' + encodeURIComponent(c.branch), { headers: h, muteHttpExceptions: true });
  if (b.getResponseCode() === 404) return 'ERROR: branch "' + c.branch + '" does not exist. The repo default branch is "' + info.default_branch + '". Set GH_BRANCH to that.';
  return 'OK: can write to ' + c.repo + ' on branch ' + c.branch + '.';
}

function publishNewEpisodes() {
  var c = cfg();
  var access = checkAccess_(c);
  if (access.indexOf('OK') !== 0) {
    Logger.log(access);
    MailApp.sendEmail(Session.getActiveUser().getEmail(), 'Courtroom Chronicles: site publish failed', access);
    throw new Error(access);
  }
  var report = [];
  var root = DriveApp.getFolderById(c.folder);
  scanFolder_(root, c, report);
  var subs = root.getFolders();
  while (subs.hasNext()) scanFolder_(subs.next(), c, report);

  Logger.log(report.join('\n') || 'No epNNN.json files found');
  var changed = report.filter(function (r) { return /^(added|updated)/.test(r); });
  var failed = report.filter(function (r) { return r.indexOf('FAILED') === 0; });
  if (failed.length) {
    MailApp.sendEmail(Session.getActiveUser().getEmail(), 'Courtroom Chronicles: site publish failed', failed.join('\n'));
  }
  return changed.length + ' published, ' + failed.length + ' failed';
}

function scanFolder_(folder, c, report) {
  var files = folder.getFiles();
  while (files.hasNext()) {
    var f = files.next();
    if (/^ep\d{3}\.json$/i.test(f.getName())) {
      try {
        report.push(publishEpisodeFile(f, c));
      } catch (e) {
        report.push('FAILED ' + f.getName() + ': ' + e.message);
      }
    }
  }
}

function publishEpisodeFile(file, c) {
  var text = file.getBlob().getDataAsString('UTF-8').trim();
  text = text.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '');
  var ep = JSON.parse(text); // fails loudly if the JSON is broken

  if (!/^ep\d{3}$/i.test(ep.id || '')) throw new Error("'id' must look like ep012");
  ['title', 'hook', 'summary'].forEach(function (k) {
    if (!ep[k] || (Array.isArray(ep[k]) && !ep[k].length)) throw new Error("missing '" + k + "'");
  });
  var name = ep.id.toLowerCase() + '.json';
  if (file.getName().toLowerCase() !== name) throw new Error('file name does not match id ' + ep.id);

  var api = 'https://api.github.com/repos/' + c.repo + '/contents/data/episodes/' + name;
  var headers = { Authorization: 'Bearer ' + c.token, Accept: 'application/vnd.github+json' };
  var cur = UrlFetchApp.fetch(api + '?ref=' + c.branch, { headers: headers, muteHttpExceptions: true });
  var sha = null;
  var body = JSON.stringify(ep, null, 2) + '\n';

  if (cur.getResponseCode() === 200) {
    var j = JSON.parse(cur.getContentText());
    sha = j.sha;
    var old = Utilities.newBlob(Utilities.base64Decode(j.content.replace(/\n/g, ''))).getDataAsString('UTF-8');
    if (JSON.stringify(JSON.parse(old)) === JSON.stringify(ep)) return 'unchanged ' + name;
  } else if (cur.getResponseCode() !== 404) {
    throw new Error('GitHub read failed: ' + cur.getContentText());
  }

  var payload = {
    message: (sha ? 'Update ' : 'Add ') + ep.id,
    content: Utilities.base64Encode(body, Utilities.Charset.UTF_8),
    branch: c.branch
  };
  if (sha) payload.sha = sha;
  var res = UrlFetchApp.fetch(api, {
    method: 'put', headers: headers, contentType: 'application/json',
    payload: JSON.stringify(payload), muteHttpExceptions: true
  });
  if (res.getResponseCode() >= 300) throw new Error('GitHub write failed: ' + res.getContentText());
  return (sha ? 'updated ' : 'added ') + name;
}
