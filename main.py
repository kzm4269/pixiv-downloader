import pixiv

USERNAME = 'hoge'
PASSWORD = 'huga'
SAVE_DIR = '/path/to/save/dir'

def main():
    api = pixiv.login(username=USERNAME, password=PASSWORD)

    print('---- following users ----')
    for user in api.me_following(publicity='public', per_page=5, page=1):
        print(user.id, user.name)

    print('---- following works ----')
    for work in api.me_following_works(per_page=10, page=1):
        print(work.id, work.title, work.user.name)

    print('---- donwload ---')
    downloader = pixiv.Downloader(api, SAVE_DIR)
    downloader.download_work(work_id=54238974)


if __name__ == '__main__':
    main()
