import asyncio
import aiohttp


async def scrap_page(link: str):
    async with aiohttp.ClientSession() as session_ctx:
        async with session_ctx.get(link) as response_ctx:
            print(f'Status: {response_ctx.status}')
            print(f'Content: {response_ctx.content_type}')

            html_text = await response_ctx.text()
            print(html_text)


def main():
    link = 'https://inosmi.ru/politic/20211005/250637968.html'
    loop = asyncio.get_event_loop()
    loop.run_until_complete(scrap_page(link))
    # asyncio.run.run(scrap_page(link))


if __name__ == '__main__':
    main()




