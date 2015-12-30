import enum
import itertools
import json
import logging
import re

import attrdict
import lxml.html
import scrapelib

LOGGER = logging.Logger(__name__)
LOGGER.setLevel(level=logging.DEBUG)
LOGGER.addHandler(logging.StreamHandler())


class PixivError(Exception):
    pass


class Publicity(enum.Enum):
    """画像やフォローユーザの公開/非公開"""
    PUBLIC = 'public'
    PRIVATE = 'private'


class RankingType(enum.Enum):
    """ランキングの検索対象"""
    ALL = 'all'
    ILLUST = 'illust'
    MANGA = 'manga'
    UGOIRA = 'ugoira'


class RankingMode(enum.Enum):
    """ランキングのモード"""
    DAILY = 'daily'
    WEEKLY = 'weekly'
    MONTHLY = 'monthly'
    ROOKIE = 'rookie'
    ORIGINAL = 'original'
    MALE = 'male'
    FEMALE = 'female'
    DAILY_R18 = 'daily_r18'
    WEEKLY_R18 = 'weekly_r18'
    MALE_R18 = 'male_r18'
    FEMALE_R18 = 'female_r18'
    R18G = 'r18g'


class WorkType(enum.Enum):
    """投稿作品の種類"""
    ILLUST = 'illust'
    MANGA = 'manga'
    UGOIRA = 'ugoira'
    NOVEL = 'novel'


def worktype(info_json):
    """
    投稿作品の種類を判定する
    :param info_json: 作品情報
    :return: WorkType
    """
    if 'text_length' in info_json:
        return WorkType.NOVEL
    if info_json.is_manga:
        return WorkType.MANGA
    try:
        if 'ugoira600x600' in info_json.metadata.zip_urls:
            return WorkType.UGOIRA
    except AttributeError:
        pass
    return WorkType.ILLUST


class PixivApiBase(object):
    _REFERER = 'http://www.pixiv.net/'
    _USER_AGENT = 'PixivIOSApp/5.8.3'
    _CLIENT_ID = 'bYGKuGVw91e0NMfPGp44euvGt59s'
    _CLIENT_SECRET = 'HP3RmkgAmEGro0gn1x9ioawQE8WMfvLXDz3ZqxpK'

    def __init__(self, username, password):
        self.headers = {'Referer': self._REFERER, 'User-Agent': self._USER_AGENT}
        self.cookies = dict()
        self.client_data = {'client_id': self._CLIENT_ID, 'client_secret': self._CLIENT_SECRET}
        self.scraper = scrapelib.Scraper(retry_attempts=3)

        self._authenticate(username=username, password=password)

    def _authenticate(self, username=None, password=None, refresh_token=None):
        # authentication url
        url = 'https://oauth.secure.pixiv.net/auth/token'

        # authentication data
        data = dict(**self.client_data)
        if username and password:
            data['grant_type'] = 'password'
            data['username'] = username
            data['password'] = password
        elif refresh_token:
            data['grant_type'] = 'refresh_token'
            data['refresh_token'] = refresh_token
        else:
            raise PixivError('no password or refresh_token is set. authentication failed.')

        # authentication request
        token = self.request_json('post', url, data=data)

        # update tokens
        self._access_token = token.response.access_token
        self._refresh_token = token.response.refresh_token
        self.headers.update({'Authorization': 'Bearer {}'.format(self._access_token)})

    def refresh(self):
        self._authenticate(refresh_token=self._refresh_token)

    def request(self, method, url, **kwargs):
        # request
        try:
            result = self.scraper.request(method, url, cookies=self.cookies, headers=self.headers, **kwargs)
        except scrapelib.HTTPError as e:
            body = json.loads(e.body, object_hook=attrdict.AttrDict)
            if 'errors' in body:
                raise PixivError(body.errors.system.message)
            else:
                raise PixivError

        # update cookie
        if 'Set-Cookie' in result.headers:
            for m in re.finditer(r'(\S+)=(\S+);', result.headers['Set-Cookie']):
                self.cookies.update({m.group(1): m.group(2)})

        return result

    def request_json(self, method, url, **kwargs):
        result = self.request(method, url, **kwargs)
        try:
            result_json = json.loads(result.text, object_hook=attrdict.AttrDict)
        except Exception:
            raise PixivError

        return result_json

    def request_singlepage(self, method, url, params=None, data=None):
        res = self.request_json(method, url, params=params, data=data)
        assert 'pagination' not in res
        assert len(res.response) == 1
        return res.response[0]

    def request_multipages(self, method, url, params):
        if params['page']:
            return self.request_json(method, url, params=params).response

        request = self.request_json

        class Response(object):
            @staticmethod
            def _request_page(p):
                return request(method, url, params=dict(params, page=p))

            def page(self, p):
                return self._request_page(p).response

            def pageiter(self):
                p = 1
                while p:
                    res = self._request_page(p)
                    p = res.pagination.next
                    yield res.response

            def pagination(self):
                return self._request_page(1).pagination

            def __iter__(self):
                return itertools.chain.from_iterable(self.pageiter())

        return Response()


class Me(object):
    def __init__(self, api):
        assert isinstance(api, PixivApiBase)
        self.api = api

    def following_users(self, page=None, per_page=100, publicity='public'):
        url = 'https://public-api.secure.pixiv.net/v1/me/following.json'
        params = {
            'page': page,
            'per_page': per_page,
            'publicity': publicity,
        }
        return self.api.request_multipages('get', url, params)

    def following_works(self, page=None, per_page=100,
                        image_sizes=('px_128x128', 'px_480mw', 'large'),
                        include_stats=True, include_sanity_level=True):
        url = 'https://public-api.secure.pixiv.net/v1/me/following/works.json'
        params = {
            'page': page,
            'per_page': per_page,
            'image_sizes': ','.join(image_sizes),
            'include_stats': include_stats,
            'include_sanity_level': include_sanity_level,
        }
        return self.api.request_multipages('get', url, params)

    def favorite_works(self, page=None, per_page=100, publicity='public',
                       image_sizes=('px_128x128', 'px_480mw', 'large')):
        url = 'https://public-api.secure.pixiv.net/v1/me/favorite_works.json'
        params = {
            'page': page,
            'per_page': per_page,
            'publicity': publicity,
            'image_sizes': ','.join(image_sizes),
        }
        return self.api.request_multipages('get', url, params)

    def feeds(self, feed_type='touch_nottext', relation='all', show_r18=True, max_id=None):
        url = 'https://public-api.secure.pixiv.net/v1/me/feeds.json'
        params = {
            'type': feed_type,
            'relation': relation,
            'show_r18': show_r18,
        }
        if max_id:
            params['max_id'] = max_id
        return self.api.request_singlepage('get', url, params=params)

    def add_following_users(self, target_user_id, publicity='public'):
        url = 'https://public-api.secure.pixiv.net/v1/me/favorite-users.json'
        params = {
            'target_user_id': target_user_id,
            'publicity': publicity,
        }
        return self.api.request_json('post', url, params=params)

    def delete_following_users(self, delete_ids, publicity='public'):
        url = 'https://public-api.secure.pixiv.net/v1/me/favorite-users.json'
        params = {
            'delete_ids': ",".join(map(str, delete_ids)),
            'publicity': publicity,
        }
        return self.api.request_json('post', url, params=params)

    def add_favorite_works(self, work_id, publicity='public'):
        url = 'https://public-api.secure.pixiv.net/v1/me/favorite_works.json'
        params = {
            'work_id': work_id,
            'publicity': publicity,
        }
        return self.api.request_json('post', url, params=params)

    def delete_favorite_works(self, ids, publicity='public'):
        url = 'https://public-api.secure.pixiv.net/v1/me/favorite_works.json'
        params = {
            'ids': ",".join(map(str, ids)),
            'publicity': publicity,
        }
        return self.api.request_json('post', url, params=params)


class User(object):
    def __init__(self, api, user_id):
        assert isinstance(api, PixivApiBase)
        self.api = api
        self.id = user_id

    def profile(self,
                profile_image_sizes=('px_170x170', 'px_50x50'),
                image_sizes=('px_128x128', 'small', 'medium', 'large', 'px_480mw'),
                include_stats=True, include_profile=True, include_workspace=True, include_contacts=True):
        url = 'https://public-api.secure.pixiv.net/v1/users/{:d}.json'.format(self.id)
        params = {
            'profile_image_sizes': ','.join(profile_image_sizes),
            'image_sizes': ','.join(image_sizes),
            'include_stats': include_stats,
            'include_profile': include_profile,
            'include_workspace': include_workspace,
            'include_contacts': include_contacts,
        }
        return self.api.request_singlepage('get', url, params=params)

    def works(self, page=None, per_page=100,
              image_sizes=('px_128x128', 'px_480mw', 'large'),
              include_stats=True, include_sanity_level=True):
        url = 'https://public-api.secure.pixiv.net/v1/users/{:d}/works.json'.format(self.id)
        params = {
            'page': page,
            'per_page': per_page,
            'include_stats': include_stats,
            'include_sanity_level': include_sanity_level,
            'image_sizes': ','.join(image_sizes),
        }
        return self.api.request_multipages('get', url, params)

    def novels(self, page=None, per_page=100,
               include_stats=True, include_sanity_level=True):
        url = 'https://public-api.secure.pixiv.net/v1/users/{:d}/novels.json'.format(self.id)
        params = {
            'page': page,
            'per_page': per_page,
            'include_stats': include_stats,
            'include_sanity_level': include_sanity_level,
        }
        return self.api.request_multipages('get', url, params)

    def favorite_works(self, page=None, per_page=100,
                       image_sizes=('px_128x128', 'px_480mw', 'large'),
                       include_sanity_level=True):
        url = 'https://public-api.secure.pixiv.net/v1/users/{:d}/favorite_works.json'.format(self.id)
        params = {
            'page': page,
            'per_page': per_page,
            'include_sanity_level': include_sanity_level,
            'image_sizes': ','.join(image_sizes),
        }
        return self.api.request_multipages('get', url, params)

    def feeds(self, feed_type='touch_nottext', relation='all', show_r18=1, max_id=None):
        url = 'https://public-api.secure.pixiv.net/v1/users/{:d}/feeds.json'.format(self.id)
        params = {
            'type': feed_type,
            'relation': relation,
            'show_r18': show_r18,
        }
        if max_id:
            params['max_id'] = max_id
        return self.api.request_singlepage('get', url, params=params)

    def following_users(self, page=None, per_page=100):
        url = 'https://public-api.secure.pixiv.net/v1/users/{:d}/following.json'.format(self.id)
        params = {
            'page': page,
            'per_page': per_page,
        }
        return self.api.request_multipages('get', url, params)


class Work(object):
    def __init__(self, api, work_id):
        assert isinstance(api, PixivApiBase)
        self.api = api
        self.id = work_id

    def info(self,
             image_sizes=('px_128x128', 'small', 'medium', 'large', 'px_480mw'),
             include_stats=True):
        url = 'https://public-api.secure.pixiv.net/v1/works/{:d}.json'.format(self.id)
        params = {
            'image_sizes': ','.join(image_sizes),
            'include_stats': include_stats,
        }
        return self.api.request_singlepage('get', url, params=params)

    def comments(self, page=None, per_page=100):
        url = 'https://public-api.secure.pixiv.net/v1/works/{:d}/comments.json'.format(self.id)
        params = {
            'page': page,
            'per_page': per_page,
        }
        return self.api.request_multipages('get', url, params)

    def bookmarks(self, page=None, per_page=100):
        url = 'https://public-api.secure.pixiv.net/v1/works/{:d}/favorited.json'.format(self.id)
        params = {
            'page': page,
            'per_page': per_page,
        }
        return self.api.request_multipages('get', url, params)


class Novel(object):
    def __init__(self, api, novel_id):
        assert isinstance(api, PixivApiBase)
        self.api = api
        self.id = novel_id

    def info(self, image_sizes=('px_128x128', 'small', 'medium', 'large', 'px_480mw'), include_stats=True):
        url = 'https://public-api.secure.pixiv.net/v1/novels/{:d}.json'.format(self.id)
        params = {
            'image_sizes': ','.join(image_sizes),
            'include_stats': include_stats,
        }
        return self.api.request_singlepage('get', url, params=params)

    def comments(self, page=None, per_page=100):
        url = 'https://public-api.secure.pixiv.net/v1/novels/{:d}/comments.json'.format(self.id)
        params = {
            'page': page,
            'per_page': per_page,
        }
        return self.api.request_multipages('get', url, params)

    def text(self):
        # get html text
        url = 'http://www.pixiv.net/novel/show.php?id={:d}'.format(self.id)
        html_text = self.api.request('get', url).text

        # extract novel text
        novel_text = tuple(tag.text for tag in lxml.html.fromstring(html_text).xpath('//textarea')
                           if tag.attrib.get('id', None) == tag.attrib.get('name', None) == 'novel_text')
        assert len(novel_text) == 1, (self.id, html_text)
        return novel_text[0]


class PixivApi(PixivApiBase):
    def refresh(self):
        self._authenticate(refresh_token=self._refresh_token)

    def bad_words(self):
        url = 'https://public-api.secure.pixiv.net/v1.1/bad_words.json'
        return self.request_singlepage('get', url)

    @property
    def me(self):
        return Me(self)

    def user(self, users_id):
        return User(self, users_id)

    def work(self, work_id):
        return Work(self, work_id)

    def novel(self, novel_id):
        return Novel(self, novel_id)

    def ranking(self, ranking_type, mode, page=None, per_page=100, date=None,
                profile_image_sizes=('px_170x170', 'px_50x50'),
                image_sizes=('px_128x128', 'small', 'medium', 'large', 'px_480mw'),
                include_stats=True, include_sanity_level=True):
        url = 'https://public-api.secure.pixiv.net/v1/ranking/{}.json'.format(ranking_type)
        params = {
            'mode': mode,
            'page': page,
            'per_page': per_page,
            'include_stats': include_stats,
            'include_sanity_level': include_sanity_level,
            'image_sizes': ','.join(image_sizes),
            'profile_image_sizes': ','.join(profile_image_sizes),
        }
        if date:
            params['date'] = date
        return self.request_multipages('get', url, params)

    def search_works(self, query, page=None, per_page=100, mode='text',
                     period='all', order='desc', sort='date',
                     types=('illustration', 'manga', 'ugoira'),
                     image_sizes=('px_128x128', 'px_480mw', 'large'),
                     include_stats=True, include_sanity_level=True):
        url = 'https://public-api.secure.pixiv.net/v1/search/works.json'
        params = {
            'q': query,
            'page': page,
            'per_page': per_page,
            'period': period,
            'order': order,
            'sort': sort,
            'mode': mode,
            'types': ','.join(types),
            'include_stats': include_stats,
            'include_sanity_level': include_sanity_level,
            'image_sizes': ','.join(image_sizes),
        }
        return self.request_multipages('get', url, params)

    def latest_works(self, page=None, per_page=100,
                     image_sizes=('px_128x128', 'px_480mw', 'large'),
                     profile_image_sizes=('px_170x170', 'px_50x50'),
                     include_stats=True, include_sanity_level=True):
        url = 'https://public-api.secure.pixiv.net/v1/works.json'
        params = {
            'page': page,
            'per_page': per_page,
            'include_stats': include_stats,
            'include_sanity_level': include_sanity_level,
            'image_sizes': ','.join(image_sizes),
            'profile_image_sizes': ','.join(profile_image_sizes),
        }
        return self.request_multipages('get', url, params)


def login(username, password):
    return PixivApi(username, password)
