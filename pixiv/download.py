import datetime
import io
import json
import logging
import os
import posixpath
import re
import urllib.parse
import urllib.request
import time

import lxml.html

from . import core

LOGGER = logging.Logger(__name__)
LOGGER.setLevel(level=logging.DEBUG)
LOGGER.addHandler(logging.NullHandler())


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


def _pixiv_open(scraper, url):
    fname, response = scraper.urlretrieve(url, headers={'Referer': 'http://www.pixiv.net/'})
    return io.BytesIO(response.content)


class Downloader(object):
    def __init__(self, api: core.PixivApi, outdir):
        self.api = api
        self.outdir = outdir

    def _download_raw(self, url, out, reuploaded_time=None):
        out = os.path.join(self.outdir, out)
        if _is_skippable(out, reuploaded_time):
            LOGGER.info('skip: {}'.format(out))
            return False
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with _pixiv_open(self.api._screper, url) as fi, open(out, 'wb') as fo:
            fo.write(fi.read())
        _utime(out, reuploaded_time)
        LOGGER.info('download: {}'.format(out))
        return True

    def _save_json(self, data, out):
        out = os.path.join(self.outdir, out)
        LOGGER.info('save: {}'.format(out))
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def download_work(self, work_id):
        work = self.api.works(int(work_id))
        self._save_json(work, self.work_info_outpath(work, 'json'))
        self._save_json(tuple(self.api.works_comments(work.id)), self.work_comments_outpath(work, 'json'))

        if work.is_manga:
            return self._download_manga(work)

        try:
            is_ugoira = 'ugoira600x600' in work.metadata.zip_urls
        except AttributeError:
            is_ugoira = False
        if is_ugoira:
            return self._download_ugoira(work)

        return self._download_illust(work)

    def download_novel(self, novel_id):
        novel = self.api.novels(novel_id)
        self._save_json(novel, self.novel_info_outpath(novel, 'json'))
        self._save_json(tuple(self.api.novels_comments(novel.id)), self.novel_comments_outpath(novel, 'json'))

        url = 'http://www.pixiv.net/novel/show.php?id={:d}'.format(novel.id)
        text = tuple(tag.text for tag in lxml.html.parse(url).xpath('//textarea')
                     if tag.attrib['id'] == tag.attrib['name'] == 'novel_text')
        assert len(text) == 1
        text = text[0]

        out = os.path.join(self.outdir, self.novel_outpath(novel, 'txt'))
        LOGGER.info('download: {}'.format(out))
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, 'w') as f:
            f.writelines(text)
        _utime(out, novel.reuploaded_time)

        for work_id in (m.group(1) for m in re.finditer(r'\[pixivimage:(\d+)\]', text)):
            self.download_work(work_id)

    def _download_illust(self, work):
        url = work.image_urls.large
        out = self.illust_outpath(work, _ext(url))
        self._download_raw(url, out, work.reuploaded_time)

    def _download_manga(self, work):
        for i, page in enumerate(work.metadata.pageiter):
            url = page.image_urls.large
            out = self.manga_outpath(work, i, _ext(url))
            self._download_raw(url, out, work.reuploaded_time)

    def _download_ugoira(self, work):
        url = work.metadata.zip_urls.ugoira600x600
        out = self.ugoira_outpath(work, _ext(url))
        self._download_raw(url, out, work.reuploaded_time)

    def download_user_works(self, user_id):
        self._download_user_info(user_id)
        for work in self.api.users_works(user_id):
            self.download_work(work.id)

    def download_user_novels(self, user_id):
        self._download_user_info(user_id)
        for novel in self.api.users_novels(user_id):
            self.download_novel(novel.id)

    def download_user_all(self, user_id):
        self.download_user_works(user_id)
        self.download_user_novels(user_id)

    def _download_user_info(self, user_id):
        user = self.api.users(user_id)
        self._download_user_image(user)
        self._save_json(user, self.user_info_outpath(user, 'json'))

    def _download_user_image(self, user):
        url = user.profile_image_urls.px_170x170
        out = self.user_image_outpath(user, _ext(url))
        self._download_raw(url, out)

    @staticmethod
    def illust_outpath(work, ext):
        return 'users/{:09d}/works/{:012d}.{}'.format(work.user.id, work.id, ext)

    @staticmethod
    def manga_outpath(work, page, ext):
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
    def user_info_outpath(user, ext):
        return 'users/{:09d}/info.{}'.format(user.id, ext)

    @staticmethod
    def user_image_outpath(user, ext):
        return 'users/{:09d}/image.{}'.format(user.id, ext)
