import pixiv
import json
import os

HOME = os.path.expandvars('$HOME')
SAVE_DIR = os.path.join(HOME, 'tmp/pixiv')


def main():
    with open('password.json') as f:
        password = json.load(f)
    api = pixiv.login(**password)

    downloader = pixiv.Downloader(api)
    downloader.download_work(54298454)


if __name__ == '__main__':
    main()
