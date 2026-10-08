import json, sys
import instaloader

def main():
    if len(sys.argv)==2 and sys.argv[1]=='--health': print('ok'); return 0
    if len(sys.argv)!=2: print('usage: runner.py <username>', file=sys.stderr); return 2
    username=sys.argv[1].lstrip('@').strip()
    if not username or '/' in username or ' ' in username: print('invalid username', file=sys.stderr); return 2
    loader=instaloader.Instaloader(quiet=True)
    profile=instaloader.Profile.from_username(loader.context, username)
    print(json.dumps({
      'username': profile.username, 'profile_url': f'https://www.instagram.com/{profile.username}/',
      'full_name': profile.full_name, 'biography': profile.biography, 'followers': profile.followers,
      'followees': profile.followees, 'mediacount': profile.mediacount, 'is_private': profile.is_private,
      'is_verified': profile.is_verified, 'external_url': profile.external_url,
    }, ensure_ascii=False, sort_keys=True))
    return 0
if __name__=='__main__': raise SystemExit(main())
