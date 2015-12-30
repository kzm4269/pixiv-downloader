import pixiv
import json
import os

USERNAME = 'highland2'
PASSWORD = 'PiEqual314159265'

HOME = os.path.expandvars('$HOME')
SAVE_DIR = os.path.join(HOME, 'tmp/pixiv')


def main():
    api = pixiv.login(USERNAME, PASSWORD)
    downloader = pixiv.Downloader(api, SAVE_DIR)

    for work in api.me.following_works(per_page=5, page=1):
        print(work.reuploaded_time, work.title, work.user.name)
        downloader.download_work(work.id)


if __name__ == '__main__':
    main()
