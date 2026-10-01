"""Build/install a reversible game-start allowance patch for this local copy."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import zipfile

from .core import ROOT, BUDGETS, backup_save, game_pids, log_action

from .paths import game_executable

GAME = game_executable()
WORK = ROOT / 'backups' / 'permanent'
MANIFEST = WORK / 'manifest.json'
PROFILE = ROOT / 'permanent_profile.json'
SETTINGS = 'kr6/game_settings.lua'
MAP = 'kr6/kviews_screen_map_game.lua'
SUPPORTED_MODULE_HASHES = {
    SETTINGS: '6b2d6190cbc1cd7bd51a500a986095bd40872adb0b047fe33cd7843b0b026051',
    MAP: '9c96a8a48533cc4dce7b526cc9a27c8db39040493a2376123fcc84ac24920c34',
}


def digest(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def wrappers(profile):
    tower = ','.join(str(v) for v in profile['tower_bonus'])
    hero = ','.join(str(v) for v in profile['hero_bonus'])
    settings = f'''-- GhostValue persistent allowances, original module preserved.
local settings = assert(love.filesystem.load("ghostvalue_original/game_settings.lua"))()
assert(type(settings) == "table", "GhostValue: game settings unavailable")
local function add(values, bonuses)
  assert(type(values) == "table" and #values == #bonuses, "GhostValue: configuration mismatch")
  for i, bonus in ipairs(bonuses) do values[i] = values[i] + bonus end
end
add(settings.upgrades_points_per_stage, {{{tower}}})
add(settings.skill_points_for_hero_level, {{{hero}}})
return settings
'''
    screen = f'''-- GhostValue persistent spell allowance; XP and levels unchanged.
local result = assert(love.filesystem.load("ghostvalue_original/kviews_screen_map_game.lua"))()
assert(PowerRoomView and type(PowerRoomView.get_unit_stats) == "function", "GhostValue: spell view unavailable")
local original_get_unit_stats = PowerRoomView.get_unit_stats
PowerRoomView.get_unit_stats = function(self, ...)
  local stats = original_get_unit_stats(self, ...)
  if stats and type(stats.remaining_points) == "number" then
    stats.remaining_points = stats.remaining_points + {profile['spell_bonus']}
  end
  return stats
end
return result
'''
    return {SETTINGS: settings.encode(), MAP: screen.encode()}


def installed_profile():
    """Inspect the actual archive, not a stale local installation marker."""
    if not GAME.exists():
        return None
    with zipfile.ZipFile(GAME) as z:
        if 'ghostvalue_profile.json' not in z.namelist():
            return None
        entry = z.getinfo('ghostvalue_profile.json')
        if entry.file_size > 4096:
            raise RuntimeError('Permanent patch profile is invalid')
        profile = json.loads(z.read(entry))
        for name, expected in wrappers(profile).items():
            if z.read(name) != expected:
                raise RuntimeError('Permanent patch modules changed; verify installation')
        return profile


def build(profile=None):
    if profile is None:
        history = ROOT / 'logs' / 'upgrade_candidates.json'
        if not history.exists():
            raise RuntimeError('Specify --tower-bonus, --hero-bonus and --spell-bonus; no local allowance history exists')
        state = json.loads(history.read_text())
        profile = {'tower_bonus': [a - b for a, b in zip(state['tables']['tower']['values'], BUDGETS['tower'])],
               'hero_bonus': [a - b for a, b in zip(state['tables']['hero']['values'], BUDGETS['hero'])],
               'spell_bonus': 10, 'game_version': '1.00.052'}
    if type(profile['spell_bonus']) is not int or not 0 <= profile['spell_bonus'] <= 10000:
        raise RuntimeError('Invalid spell allowance')
    for key, length in [('tower_bonus', 18), ('hero_bonus', 10)]:
        if len(profile[key]) != length or not all(type(v) is int and 0 <= v <= 10000 for v in profile[key]):
            raise RuntimeError('Invalid stored allowance profile')
    WORK.mkdir(parents=True, exist_ok=True)
    original_hash = digest(GAME)
    backup = WORK / ('original-' + original_hash[:16] + '.exe')
    with zipfile.ZipFile(GAME) as z:
        if 'ghostvalue_profile.json' in z.namelist():
            raise RuntimeError('A permanent patch is already installed; do not stack patches')
        original_modules = {SETTINGS: z.read(SETTINGS), MAP: z.read(MAP)}
        if any(hashlib.sha256(data).hexdigest() != SUPPORTED_MODULE_HASHES[name] for name, data in original_modules.items()):
            raise RuntimeError('Unsupported game modules; no patch built. Adapt and test this game version first.')
        prefix_size = min(i.header_offset for i in z.infolist())
        original_entries = {i.filename: (i.CRC, i.file_size) for i in z.infolist()}
    if backup.exists():
        if digest(backup) != original_hash:
            raise RuntimeError('Original backup does not match')
    else:
        shutil.copy2(GAME, backup)
        if digest(backup) != original_hash:
            raise RuntimeError('Backup hash mismatch')
    staged = WORK / 'Kingdom Rush Genesis.patched.exe'
    shutil.copy2(backup, staged)
    # Replace central-directory entries, retaining the executable stub and all assets.
    # Old local records are unreachable; the final ZIP has exactly one entry per name.
    with zipfile.ZipFile(staged, 'a', compression=zipfile.ZIP_DEFLATED) as z:
        z.filelist = [i for i in z.filelist if i.filename not in original_modules]
        for name in original_modules:
            del z.NameToInfo[name]
        z.writestr('ghostvalue_original/game_settings.lua', original_modules[SETTINGS])
        z.writestr('ghostvalue_original/kviews_screen_map_game.lua', original_modules[MAP])
        for name, data in wrappers(profile).items():
            z.writestr(name, data)
        z.writestr('ghostvalue_profile.json', json.dumps(profile))
    with zipfile.ZipFile(staged) as z:
        if len(z.namelist()) != len(set(z.namelist())) or z.testzip() is not None:
            raise RuntimeError('Archive integrity check failed')
        for name, expected in original_entries.items():
            if name not in original_modules:
                info = z.getinfo(name)
                if (info.CRC, info.file_size) != expected:
                    raise RuntimeError('Unexpected asset change: ' + name)
        if z.read('ghostvalue_original/game_settings.lua') != original_modules[SETTINGS] or z.read('ghostvalue_original/kviews_screen_map_game.lua') != original_modules[MAP]:
            raise RuntimeError('Preserved original module mismatch')
    with backup.open('rb') as a, staged.open('rb') as b:
        if a.read(prefix_size) != b.read(prefix_size):
            raise RuntimeError('Executable prefix changed')
    manifest = dict(profile=profile, original_hash=original_hash, patched_hash=digest(staged),
                    backup=str(backup), staged=str(staged), game=str(GAME), status='prepared')
    MANIFEST.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps(manifest, indent=2))


def install():
    if game_pids():
        raise RuntimeError('Exit the game before installing')
    m = json.loads(MANIFEST.read_text())
    if digest(GAME) != m['original_hash'] or digest(m['staged']) != m['patched_hash']:
        raise RuntimeError('Game or staged patch changed; refusing replacement')
    save_backup = backup_save()
    temp = GAME.with_name('GhostValue-install.tmp')
    if temp.exists():
        raise RuntimeError('Installation temp file already exists; inspect before retrying')
    shutil.copy2(m['staged'], temp)
    if digest(temp) != m['patched_hash'] or game_pids():
        raise RuntimeError('Final validation failed; original game was not replaced')
    os.replace(temp, GAME)
    if digest(GAME) != m['patched_hash']:
        raise RuntimeError('Installed hash mismatch; restore from original backup')
    m['status'] = 'installed'
    MANIFEST.write_text(json.dumps(m, indent=2), encoding='utf-8')
    PROFILE.write_text(json.dumps(m, indent=2), encoding='utf-8')
    log_action('permanent_allowances_installed', profile=m['profile'], save_backup=str(save_backup), original_backup=m['backup'])
    print('Installed and verified. Original game backup:', m['backup'])


def restore():
    if game_pids():
        raise RuntimeError('Exit the game before restoring')
    m = json.loads(MANIFEST.read_text())
    if digest(GAME) != m['patched_hash'] or digest(m['backup']) != m['original_hash']:
        raise RuntimeError('Files changed; refusing to overwrite a different game version')
    backup_save()
    temp = GAME.with_name('GhostValue-restore.tmp')
    if temp.exists():
        raise RuntimeError('Restore temp already exists')
    shutil.copy2(m['backup'], temp)
    if digest(temp) != m['original_hash'] or game_pids():
        raise RuntimeError('Restore validation failed')
    os.replace(temp, GAME)
    m['status'] = 'restored'
    MANIFEST.write_text(json.dumps(m, indent=2), encoding='utf-8')
    PROFILE.write_text(json.dumps(m, indent=2), encoding='utf-8')
    print('Original game restored. Excess purchased upgrades still require an in-game reset or save restoration.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['build', 'install', 'restore'])
    parser.add_argument('--tower-bonus', type=int)
    parser.add_argument('--hero-bonus', type=int)
    parser.add_argument('--spell-bonus', type=int)
    args = parser.parse_args()
    amounts = (args.tower_bonus, args.hero_bonus, args.spell_bonus)
    if any(a is not None for a in amounts):
        if args.action != 'build' or any(a is None for a in amounts):
            parser.error('All three bonus options must be supplied together with build')
        build({'tower_bonus': [args.tower_bonus] * 18, 'hero_bonus': [args.hero_bonus] * 10,
               'spell_bonus': args.spell_bonus, 'game_version': '1.00.052'})
    else:
        globals()[args.action]()
