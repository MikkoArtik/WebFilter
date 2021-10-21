from typing import List, NamedTuple
import asyncio
from asyncio import Queue

from bs4 import BeautifulSoup

import aiohttp
import aiofiles
import anyio
from async_timeout import timeout

import pymorphy2

from adapters.inosmi_ru import sanitize
from adapters.exceptions import ArticleNotFound

from text_tools import split_by_words, calculate_jaundice_rate


NEWS_SITES = ('https://inosmi.ru', )
NEGATIVE_VOC_LINK = 'https://sociation.org/words/negative/'
NEGATIVE_VOC_FILE = './charged_dict/negative_words.txt'

FILE_SOURCE, URL_SOURCE = 0, 1
IS_RUN, IS_STOP = 0, 1

FETCH_ERROR = 'FETCH_ERROR'
PARSING_ERROR = 'PARSING_ERROR'
TIMEOUT_ERROR = 'TIMEOUT'
SUCCESS_STATUS = 'OK'


class BadResponse(Exception):
    pass


class InvalidNewsLink(Exception):
    pass


class InvalidSourceType(Exception):
    pass


class TimeElapsedError(Exception):
    pass


def is_news_link(url_link: str) -> bool:
    for site in NEWS_SITES:
        if site in url_link:
            return True
    else:
        return False


async def get_negative_words_from_url(url=NEGATIVE_VOC_LINK) -> List[str]:
    vocabulary = []
    async with aiohttp.ClientSession() as session_ctx:
        async with session_ctx.get(url) as response_ctx:
            if response_ctx.status != 200:
                raise BadResponse

            page_body = await response_ctx.text()

            parser = BeautifulSoup(page_body, 'html.parser')
            words_list = parser.find(
                attrs={'class': 'associations_list self-clear'})
            for href in words_list.find_all('a'):
                vocabulary.append(href.get_text())
    return vocabulary


async def get_negative_words_from_file(fpath=NEGATIVE_VOC_FILE) -> List[str]:
    vocabulary = []
    async with aiofiles.open(fpath, 'r') as file_ctx:
        async for line in file_ctx:
            vocabulary.append(line.rstrip())
    return vocabulary


class NewsInfo(NamedTuple):
    url: str
    status: str
    rate: float = 0
    words_count: int = 0

    def __str__(self):
        return f'URL: {self.url}\n' \
               f'Статус: {self.status}\n' \
               f'Рейтинг: {self.rate}\n' \
               f'Слов в статье: {self.words_count}'


class NewsAnalyzer:
    def __init__(self, news_links: List[str], vocabulary_source=FILE_SOURCE,
                 timeout_sec=5.0):
        self.__news_links = news_links
        self.__vocabulary_source = vocabulary_source
        self.__timeout_sec = timeout_sec
        self.__work_status = IS_RUN
        self.__bad_vocabulary = []
        self.__analyser = pymorphy2.MorphAnalyzer()
        self.__news_info = Queue()

    @property
    def news_links(self) -> List[str]:
        return self.__news_links

    @property
    def vocabulary_source(self) -> int:
        return self.__vocabulary_source

    @property
    def timeout_sec(self) -> float:
        return self.__timeout_sec

    @property
    def work_status(self) -> int:
        return self.__work_status

    @property
    def analyser(self) -> pymorphy2.MorphAnalyzer:
        return self.__analyser

    async def scrap_news_page(self, url_link: str) -> str:
        if not is_news_link(url_link):
            raise ArticleNotFound

        async with aiohttp.ClientSession() as session_ctx:
            try:
                async with timeout(self.timeout_sec) as time_ctx:
                    async with session_ctx.get(url_link) as response_ctx:
                        status = response_ctx.status
                        if status != 200:
                            raise BadResponse
                        html_text = await response_ctx.text()
            except asyncio.TimeoutError:
                if time_ctx.expired:
                    raise TimeElapsedError
                else:
                    raise

            clear_text = sanitize(html_text, True)
            return clear_text

    async def get_bad_vocabulary(self) -> List[str]:
        if not self.__bad_vocabulary:
            if self.vocabulary_source == FILE_SOURCE:
                self.__bad_vocabulary = await get_negative_words_from_file()
            elif self.vocabulary_source == URL_SOURCE:
                self.__bad_vocabulary = await get_negative_words_from_url()
            else:
                raise InvalidSourceType
        return self.__bad_vocabulary

    async def get_rating(self, url_link: str):
        news_body = await self.scrap_news_page(url_link)
        news_words = split_by_words(self.analyser, news_body)
        bad_words = await self.get_bad_vocabulary()
        rate = calculate_jaundice_rate(article_words=news_words,
                                       charged_words=bad_words)
        news_info = NewsInfo(url_link, SUCCESS_STATUS, rate, len(news_words))
        self.__news_info.put_nowait(news_info)

    async def get_links_rating(self):
        async with anyio.create_task_group():
            for url in self.news_links:
                try:
                    await self.get_rating(url)
                except BadResponse:
                    news_info = NewsInfo(url, FETCH_ERROR)
                    self.__news_info.put_nowait(news_info)
                except ArticleNotFound:
                    news_info = NewsInfo(url, PARSING_ERROR)
                    self.__news_info.put_nowait(news_info)
                except TimeElapsedError:
                    news_info = NewsInfo(url, TIMEOUT_ERROR)
                    self.__news_info.put_nowait(news_info)
        self.__work_status = IS_STOP

    async def show_news_info(self):
        while self.__work_status != IS_STOP:
            news_info: NewsInfo = await self.__news_info.get()
            print(news_info)

    async def run(self):
        async with anyio.create_task_group() as task_ctx:
            task_ctx.start_soon(self.show_news_info)
            task_ctx.start_soon(self.get_links_rating)


async def main():
    links = ['https://inosmi.ru/economic/20211020/250738803.html',
             'https://inosmi.ru/economic/20211020/250737979.html',
             'https://inosmi.ru/economic/20211019/250735502.html',
             'https://inosmi.ru/economic/20211019/250734190.html',
             'https://inosmi.ru/economic/20211019/250730340.html']
    scraper = NewsAnalyzer(news_links=links, vocabulary_source=FILE_SOURCE,
                           timeout_sec=5)
    async with anyio.create_task_group() as task_ctx:
        task_ctx.start_soon(scraper.run)


if __name__ == '__main__':
    asyncio.run(main())
