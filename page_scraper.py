from typing import List, Tuple
import asyncio

from bs4 import BeautifulSoup

import aiohttp
import aiofiles

import pymorphy2

from adapters.inosmi_ru import sanitize

from text_tools import split_by_words, calculate_jaundice_rate


NEWS_SITES = ('https://inosmi.ru', )
NEGATIVE_VOC_LINK = 'https://sociation.org/words/negative/'
NEGATIVE_VOC_FILE = './charged_dict/negative_words.txt'

FILE_SOURCE, URL_SOURCE = 0, 1


class BadResponse(Exception):
    pass


class InvalidNewsLink(Exception):
    pass


class InvalidSourceType(Exception):
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


class MyScraper:
    def __init__(self, news_link: str, vocabulary_source=FILE_SOURCE):
        if not is_news_link(news_link):
            raise InvalidNewsLink

        self.__news_link = news_link
        self.__vocabulary_source = vocabulary_source
        self.__bad_vocabulary = []
        self.__analyser = pymorphy2.MorphAnalyzer()

    @property
    def news_link(self) -> str:
        return self.__news_link

    @property
    def vocabulary_source(self) -> int:
        return self.__vocabulary_source

    async def get_bad_vocabulary(self) -> List[str]:
        if not self.__bad_vocabulary:
            if self.vocabulary_source == FILE_SOURCE:
                self.__bad_vocabulary = await get_negative_words_from_file()
            elif self.vocabulary_source == URL_SOURCE:
                self.__bad_vocabulary = await get_negative_words_from_url()
            else:
                raise InvalidSourceType
        return self.__bad_vocabulary

    @property
    def analyser(self) -> pymorphy2.MorphAnalyzer:
        return self.__analyser

    async def scrap_news_page(self) -> str:
        async with aiohttp.ClientSession() as session_ctx:
            async with session_ctx.get(self.news_link) as response_ctx:
                html_text = await response_ctx.text()
                clear_text = sanitize(html_text, True)
                return clear_text

    async def get_rating(self) -> Tuple[float, int]:
        news_body = await self.scrap_news_page()
        news_words = split_by_words(self.analyser, news_body)
        bad_words = await self.get_bad_vocabulary()
        rate = calculate_jaundice_rate(article_words=news_words,
                                       charged_words=bad_words)
        return rate, len(news_words)


async def main():
    link = 'https://inosmi.ru/politic/20211013/250695120.html'

    scraper = MyScraper(news_link=link, vocabulary_source=URL_SOURCE)
    rate, count = await scraper.get_rating()
    print(rate, count)


if __name__ == '__main__':
    asyncio.run(main())
