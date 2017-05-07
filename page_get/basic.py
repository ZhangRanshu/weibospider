# coding:utf-8
import sys
import time
import requests
from tasks import login
from headers import headers
from logger.log import crawler
from db.redis_db import Urls
from db.redis_db import Cookies
from db.login_info import freeze_account, get_login_info
from page_parse.basic import is_403, is_404, is_complete
from decorator.decorators import timeout_decorator, timeout
from config.conf import get_timeout, get_crawl_interal, get_excp_interal, get_max_retries


time_out = get_timeout()
interal = get_crawl_interal()
max_retries = get_max_retries()
excp_interal = get_excp_interal()


# 每次抓取都从redis中随机取一个cookie以降低被封号的危险，但是还没验证不同ip对账号的影响
# todo 验证代理ip使用cookie访问用户信息会不会出现验证码
@timeout(200)
@timeout_decorator
def get_page(url, user_verify=True, need_login=True):
    """
    :param url: 待出现
    :param user_verify: 是否为可能出现验证码的页面(ajax连接不会出现验证码，如果是请求微博或者用户信息可能出现验证码)，否为抓取转发的ajax连接
    :param need_login: 抓取页面是否需要登录，这样做可以减小一些账号的压力
    :return: 返回请求的数据，如果出现404或者403,或者是别的异常，都返回空字符串
    """
    crawler.info('本次抓取的url为{url}'.format(url=url))
    count = 0
    latest_name_cookies = None

    while count < max_retries:

        if need_login:
            # 每次重试的时候都换cookies,并且和上次不同
            name_cookies = Cookies.fetch_cookies()

            if name_cookies is None:
                crawler.warning('cookie池中不存在cookie，正在检查是否有可用账号')
                rs = get_login_info()
                if len(rs) == 0:
                    crawler.error('账号均不可用，请检查账号健康状况')
                    sys.exit(-1)
                else:
                    # 如果有可用账号，那么就拿来登录
                    crawler.info('重新获取cookie中...')
                    login.excute_login_task()
                    time.sleep(10)

            if name_cookies == latest_name_cookies:
                continue

            latest_name_cookies = name_cookies

        try:
            if need_login:
                resp = requests.get(url, headers=headers, cookies=name_cookies[1], timeout=time_out, verify=False)
            else:
                resp = requests.get(url, headers=headers, timeout=time_out, verify=False)
            page = resp.text
            if page:
                page = page.encode('utf-8', 'ignore').decode('utf-8')
            else:
                continue

            # 每次抓取过后程序sleep的时间，降低封号危险
            time.sleep(interal)

            if user_verify:
                if 'unfreeze' in resp.url or is_403(page):
                    crawler.warning('账号{}已经被冻结'.format(name_cookies[0]))
                    freeze_account(name_cookies[0])
                    Cookies.delete_cookies(name_cookies[0])
                    count += 1
                    continue

                if not is_complete(page):
                    count += 1
                    continue

                if is_404(page):
                    crawler.warning('url为{url}的连接不存在'.format(url=url))
                    return ''

        except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError, AttributeError) as e:
            crawler.warning('抓取{}出现异常，具体信息是{}'.format(url, e))
            count += 1
            time.sleep(excp_interal)

        else:
            Urls.store_crawl_url(url, 1)
            return page

    crawler.warning('抓取{}已达到最大重试次数，请在redis的失败队列中查看该url并检查原因'.format(url))
    Urls.store_crawl_url(url, 0)
    return ''

__all__ = ['get_page']