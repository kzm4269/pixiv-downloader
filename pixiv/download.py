import datetime
import json
import logging
import os
import posixpath
import re
import time
import urllib.parse
import urllib.request

from . import api

LOGGER = logging.Logger(__name__)
LOGGER.setLevel(level=logging.DEBUG)
LOGGER.addHandler(logging.StreamHandler())


def _basename(url):
    return posixpath.basename(urllib.parse.urlparse(url).path)


def _ext(url):
    return os.path.splitext(url)[-1][1:]


def _datetime(uploaded_time):
    return datetime.datetime.strptime(uploaded_time, '%Y-%m-%d %H:%M:%S')


def _utime(path, uploaded_time=None):
    if uploaded_time is None:
        return os.utime(path, None)
    os.utime(path, (datetime.datetime.now().timestamp(), _datetime(uploaded_time).timestamp()))


def _is_skippable(fname, uploaded_time):
    if uploaded_time is None or not os.path.exists(fname):
        return False
    return time.mktime(_datetime(uploaded_time).timetuple()) <= os.path.getmtime(fname)


class Downloader(object):
    def __init__(self, api_: api.PixivApi, outdir=None):
        self.api = api_
        self.outdir = outdir or ''

    @staticmethod
    def _setup_dir(out):
        os.makedirs(os.path.dirname(out), exist_ok=True)

    def _download_raw(self, url, out, reuploaded_time=None):
        out = os.path.join(self.outdir, out)
        if _is_skippable(out, reuploaded_time):
            LOGGER.info('{} -> skip'.format(out))
            return

        LOGGER.info('{} -> download'.format(out))
        self._setup_dir(out)
        data = self.api.request('get', url).content
        with open(out, 'wb') as fo:
            fo.write(data)
        _utime(out, reuploaded_time)

    def _save_json(self, data, out):
        out = os.path.join(self.outdir, out)
        LOGGER.info('{} -> download'.format(out))
        self._setup_dir(out)
        with open(out, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def download_work(self, work_id):
        info = self.api.work(int(work_id)).info()
        self._save_json(info, self.work_info_outpath(info, 'json'))
        self._save_json(tuple(self.api.work(info.id).comments()), self.work_comments_outpath(info, 'json'))

        if info.type == 'ugoira':
            self._download_ugoira(info)
        elif info.page_count == 1:
            self._download_singlepage(info)
        else:
            self._download_multipage(info)

    def download_novel(self, novel_id):
        info = self.api.novel(novel_id).info()
        self._save_json(info, self.novel_info_outpath(info, 'json'))
        self._save_json(tuple(self.api.novel(info.id).comments()), self.novel_comments_outpath(info, 'json'))

        novel_text = self.api.novel(novel_id).text()

        # file name
        out = os.path.join(self.outdir, self.novel_outpath(info, 'txt'))
        if _is_skippable(out, info.reuploaded_time):
            LOGGER.info('{} -> skip'.format(out))
            return

        # save
        LOGGER.info('{} -> download'.format(out))
        self._setup_dir(out)
        with open(out, 'w') as f:
            f.writelines(novel_text)
        _utime(out, info.reuploaded_time)

        # download artworks
        for m in re.finditer(r'\[pixivimage:(\d+)\]', novel_text):
            self.download_work(m.group(1))

    def _download_singlepage(self, info):
        url = info.image_urls.large
        out = self.siglepage_outpath(info, _ext(url))
        self._download_raw(url, out, info.reuploaded_time)

    def _download_multipage(self, info):
        for i, page in enumerate(info.metadata.pages):
            url = page.image_urls.large
            out = self.multipage_outpath(info, i, _ext(url))
            self._download_raw(url, out, info.reuploaded_time)

    def _download_ugoira(self, info):
        url = info.metadata.zip_urls.ugoira600x600
        out = self.ugoira_outpath(info, _ext(url))
        self._download_raw(url, out, info.reuploaded_time)

    def download_users_works(self, user_id):
        self._download_users_profile(user_id)
        for work in self.api.user(user_id).works():
            self.download_work(work.id)

    def download_users_novels(self, user_id):
        self._download_users_profile(user_id)
        for novel in self.api.user(user_id).novels():
            self.download_novel(novel.id)

    def download_users_all(self, user_id):
        self.download_users_works(user_id)
        self.download_users_novels(user_id)

    def _download_users_profile(self, user_id):
        prof = self.api.user(user_id).profile()
        self._save_json(prof, self.users_prof_outpath(prof, 'json'))
        self._download_users_image(prof)

    def _download_users_image(self, prof):
        url = prof.profile_image_urls.px_170x170
        out = self.users_image_outpath(prof, _ext(url))
        self._download_raw(url, out)

    @staticmethod
    def siglepage_outpath(work, ext):
        return 'users/{:09d}/works/{:012d}.{}'.format(work.user.id, work.id, ext)

    @staticmethod
    def multipage_outpath(work, page, ext):
        return 'users/{:09d}/works/{:012d}_{:04d}.{}'.format(work.user.id, work.id, page, ext)

    @staticmethod
    def ugoira_outpath(work, ext):
        return 'users/{:09d}/works/{:012d}.{}'.format(work.user.id, work.id, ext)

    @staticmethod
    def novel_outpath(novel, ext):
        return 'users/{:09d}/novels/{:012d}.{}'.format(novel.user.id, novel.id, ext)

    @staticmethod
    def work_info_outpath(work, ext):
        return 'users/{:09d}/works/{:012d}_info.{}'.format(work.user.id, work.id, ext)

    @staticmethod
    def novel_info_outpath(novel, ext):
        return 'users/{:09d}/novels/{:012d}_info.{}'.format(novel.user.id, novel.id, ext)

    @staticmethod
    def work_comments_outpath(work, ext):
        return 'users/{:09d}/works/{:012d}_comments.{}'.format(work.user.id, work.id, ext)

    @staticmethod
    def novel_comments_outpath(novel, ext):
        return 'users/{:09d}/novels/{:012d}_comments.{}'.format(novel.user.id, novel.id, ext)

    @staticmethod
    def users_prof_outpath(user, ext):
        return 'users/{:09d}/prof.{}'.format(user.id, ext)

    @staticmethod
    def users_image_outpath(user, ext):
        return 'users/{:09d}/image.{}'.format(user.id, ext)
