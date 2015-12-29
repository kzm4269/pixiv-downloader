import enum
import itertools
import json
import logging

import attrdict
import scrapelib

LOGGER = logging.Logger(__name__)
LOGGER.setLevel(level=logging.DEBUG)
LOGGER.addHandler(logging.NullHandler())


class PixivError(Exception):
    pass


class Publicity(enum.Enum):
    PUBLIC = 'public'
    PRIVATE = 'private'


class RankingType(enum.Enum):
    ALL = 'all'
    ILLUST = 'illust'
    MANGA = 'manga'
    UGOIRA = 'ugoira'


class RankingMode(enum.Enum):
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
    ILLUST = 'illust'
    MANGA = 'manga'
    UGOIRA = 'ugoira'
    NOVEL = 'novel'


def worktype(info):
    if 'text_length' in info:
        return WorkType.NOVEL
    if info.is_manga:
        return WorkType.MANGA
    try:
        is_ugoira = 'ugoira600x600' in info.metadata.zip_urls
    except AttributeError:
        is_ugoira = False
    if is_ugoira:
        return WorkType.UGOIRA
    return WorkType.ILLUST


class PixivApi(object):
    def __init__(self, referer, user_agent, client_id, client_secret, username, password):
        self._client_id = client_id
        self._client_secret = client_secret
        self._headers = {'Referer': referer, 'User-Agent': user_agent}
        self._screper = scrapelib.Scraper(header_func=lambda url: self._headers)

        self._authenticate(username=username, password=password)
        LOGGER.info('login: {}'.format(username))

    def _authenticate(self, username=None, password=None, refresh_token=None):
        url = 'https://oauth.secure.pixiv.net/auth/token'

        data = {'client_id': self._client_id, 'client_secret': self._client_secret}
        if username and password:
            data['grant_type'] = 'password'
            data['username'] = username
            data['password'] = password
        elif refresh_token:
            data['grant_type'] = 'refresh_token'
            data['refresh_token'] = refresh_token
        else:
            raise PixivError('no password or refresh_token is set. authentication failed.')

        token = self._request('post', url, data=data)
        self._access_token = token.response.access_token
        self._refresh_token = token.response.refresh_token
        
        self._headers.update({'Authorization': 'Bearer {}'.format(self._access_token)})

    def _request(self, method, url, **kwargs):
        try:
            res = self._screper.request(method, url, **kwargs)
        except scrapelib.HTTPError as e:
            body = json.loads(e.body)
            if 'errors' in body:
                raise PixivError(body['errors']['system']['message'])
            else:
                raise PixivError

        try:
            text = json.loads(res.text, object_hook=attrdict.AttrDict)
        except Exception:
            raise PixivError

        return text

    def _request_singlepage(self, method, url, params=None, data=None):
        res = self._request(method, url, params=params, data=data)
        if isinstance(res.response, dict):
            return res.response
        return res.response[0]

    def _request_multipages(self, method, url, params):
        if params['page']:
            return self._request(method, url, params=params).response

        request = self._request

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

    def bad_words(self):
        url = 'https://public-api.secure.pixiv.net/v1.1/bad_words.json'
        return self._request_singlepage('get', url)

    def works(self, work_id,
              image_sizes=('px_128x128', 'small', 'medium', 'large', 'px_480mw'),
              include_stats=True):
        url = 'https://public-api.secure.pixiv.net/v1/works/{:d}.json'.format(work_id)
        params = {
            'image_sizes': ','.join(image_sizes),
            'include_stats': include_stats,
        }
        return self._request_singlepage('get', url, params=params)

    def works_comments(self, work_id, page=None, per_page=100):
        url = 'https://public-api.secure.pixiv.net/v1/works/{:d}/comments.json'.format(work_id)
        params = {
            'page': page,
            'per_page': per_page,
        }
        return self._request_multipages('get', url, params)

    def novels(self, novel_id,
               image_sizes=('px_128x128', 'small', 'medium', 'large', 'px_480mw'),
               include_stats=True):
        url = 'https://public-api.secure.pixiv.net/v1/novels/{:d}.json'.format(novel_id)
        params = {
            'image_sizes': ','.join(image_sizes),
            'include_stats': include_stats,
        }
        return self._request_singlepage('get', url, params=params)

    def novels_comments(self, work_id, page=None, per_page=100):
        url = 'https://public-api.secure.pixiv.net/v1/novels/{:d}/comments.json'.format(work_id)
        params = {
            'page': page,
            'per_page': per_page,
        }
        return self._request_multipages('get', url, params)

    def users(self, user_id,
              profile_image_sizes=('px_170x170', 'px_50x50'),
              image_sizes=('px_128x128', 'small', 'medium', 'large', 'px_480mw'),
              include_stats=True, include_profile=True, include_workspace=True, include_contacts=True):
        url = 'https://public-api.secure.pixiv.net/v1/users/{:d}.json'.format(user_id)
        params = {
            'profile_image_sizes': ','.join(profile_image_sizes),
            'image_sizes': ','.join(image_sizes),
            'include_stats': include_stats,
            'include_profile': include_profile,
            'include_workspace': include_workspace,
            'include_contacts': include_contacts,
        }
        return self._request_singlepage('get', url, params=params)

    def me_feeds(self, type_='touch_nottext', relation='all', show_r18=True, max_id=None):
        url = 'https://public-api.secure.pixiv.net/v1/me/feeds.json'
        params = {
            'type': type_,
            'relation': relation,
            'show_r18': show_r18,
        }
        if max_id:
            params['max_id'] = max_id
        return self._request_singlepage('get', url, params=params)

    def me_favorite_works(self, page=None, per_page=100, publicity='public',
                          image_sizes=('px_128x128', 'px_480mw', 'large')):
        url = 'https://public-api.secure.pixiv.net/v1/me/favorite_works.json'
        params = {
            'page': page,
            'per_page': per_page,
            'publicity': publicity,
            'image_sizes': ','.join(image_sizes),
        }
        return self._request_multipages('get', url, params)

    def me_following_works(self, page=None, per_page=100,
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
        return self._request_multipages('get', url, params)

    def me_following(self, page=None, per_page=100, publicity='public'):
        url = 'https://public-api.secure.pixiv.net/v1/me/following.json'
        params = {
            'page': page,
            'per_page': per_page,
            'publicity': publicity,
        }
        return self._request_multipages('get', url, params)

    def users_works(self, user_id, page=None, per_page=100,
                    image_sizes=('px_128x128', 'px_480mw', 'large'),
                    include_stats=True, include_sanity_level=True):
        url = 'https://public-api.secure.pixiv.net/v1/users/{:d}/works.json'.format(user_id)
        params = {
            'page': page,
            'per_page': per_page,
            'include_stats': include_stats,
            'include_sanity_level': include_sanity_level,
            'image_sizes': ','.join(image_sizes),
        }
        return self._request_multipages('get', url, params)

    def users_novels(self, user_id, page=None, per_page=100,
                     include_stats=True, include_sanity_level=True):
        url = 'https://public-api.secure.pixiv.net/v1/users/{:d}/novels.json'.format(user_id)
        params = {
            'page': page,
            'per_page': per_page,
            'include_stats': include_stats,
            'include_sanity_level': include_sanity_level,
        }
        return self._request_multipages('get', url, params)

    def users_favorite_works(self, user_id, page=None, per_page=100,
                             image_sizes=('px_128x128', 'px_480mw', 'large'),
                             include_sanity_level=True):
        url = 'https://public-api.secure.pixiv.net/v1/users/{:d}/favorite_works.json'.format(user_id)
        params = {
            'page': page,
            'per_page': per_page,
            'include_sanity_level': include_sanity_level,
            'image_sizes': ','.join(image_sizes),
        }
        return self._request_multipages('get', url, params)

    def users_feeds(self, user_id, type_='touch_nottext', relation='all', show_r18=1, max_id=None):
        url = 'https://public-api.secure.pixiv.net/v1/users/{:d}/feeds.json'.format(user_id)
        params = {
            'type': type_,
            'relation': relation,
            'show_r18': show_r18,
        }
        if max_id:
            params['max_id'] = max_id
        return self._request_singlepage('get', url, params=params)

    def users_following(self, user_id, page=None, per_page=100):
        url = 'https://public-api.secure.pixiv.net/v1/users/{:d}/following.json'.format(user_id)
        params = {
            'page': page,
            'per_page': per_page,
        }
        return self._request_multipages('get', url, params)

    def ranking(self, type_, mode, page=None, per_page=100, date=None,
                profile_image_sizes=('px_170x170', 'px_50x50'),
                image_sizes=('px_128x128', 'small', 'medium', 'large', 'px_480mw'),
                include_stats=True, include_sanity_level=True):
        url = 'https://public-api.secure.pixiv.net/v1/ranking/{}.json'.format(type_)
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
        return self._request_multipages('get', url, params)

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
        return self._request_multipages('get', url, params)

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
        return self._request_multipages('get', url, params)

    def me_favorite_works_post(self, work_id, publicity='public'):
        url = 'https://public-api.secure.pixiv.net/v1/me/favorite_works.json'
        params = {
            'work_id': work_id,
            'publicity': publicity,
        }
        return self._request('post', url, params=params)

    def me_favorite_works_delete(self, ids, publicity='public'):
        url = 'https://public-api.secure.pixiv.net/v1/me/favorite_works.json'
        params = {
            'ids': ",".join(map(str, ids)),
            'publicity': publicity,
        }
        return self._request('post', url, params=params)

    def me_favorite_users_post(self, target_user_id, publicity='public'):
        url = 'https://public-api.secure.pixiv.net/v1/me/favorite-users.json'
        params = {
            'target_user_id': target_user_id,
            'publicity': publicity,
        }
        return self._request('post', url, params=params)

    def me_favorite_users_delete(self, delete_ids, publicity='public'):
        url = 'https://public-api.secure.pixiv.net/v1/me/favorite-users.json'
        params = {
            'delete_ids': ",".join(map(str, delete_ids)),
            'publicity': publicity,
        }
        return self._request('post', url, params=params)


def login(username, password):
    return PixivApi(referer='http://www.pixiv.net/',
                    user_agent='PixivIOSApp/5.8.3',
                    client_id='bYGKuGVw91e0NMfPGp44euvGt59s',
                    client_secret='HP3RmkgAmEGro0gn1x9ioawQE8WMfvLXDz3ZqxpK',
                    username=username,
                    password=password)
