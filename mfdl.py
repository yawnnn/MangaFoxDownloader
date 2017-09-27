#!/usr/bin/env python
# encoding: utf-8

import sys
import argparse
import os
import urllib.request
import glob
import shutil
import re
import time
import requests
from itertools import filterfalse
from zipfile import ZipFile
from functools import reduce
from bs4 import BeautifulSoup
from contextlib import closing
from collections import OrderedDict

from io import StringIO
import gzip

URL_BASE = "http://mangafox.me/"
#http://mangafox/manga/anime/v/c/p

def get_page_soup(url):
    """Download a page and return a BeautifulSoup object of the html"""
    response = urllib.request.urlopen(url)
    
    page_content = ""
    if response.info().get('Content-Encoding') == 'gzip':
        gzipFile = gzip.GzipFile(fileobj=response)
        page_content = gzipFile.read()
    else:
        page_content = response.read()

    soup_page = BeautifulSoup(page_content, "html.parser")

    return soup_page

def get_chapter_urls(manga_name):
    """Get the chapter list for a manga"""
    replace = lambda s, k: s.replace(k, '_')
    manga_url = reduce(replace, [' ', '-'], manga_name.lower())
    url = '{0}manga/{1}'.format(URL_BASE, manga_url)
    print('Url: ' + url)
    soup = get_page_soup(url)
    manga_does_not_exist = soup.find('form', {'id': 'searchform'})
    if manga_does_not_exist:
        search_sort_options = 'sort=views&order=za'
        url = '{0}/search.php?name={1}&{2}'.format(URL_BASE,
                                                   manga_url,
                                                   search_sort_options)
        soup = get_page_soup(url)
        results = soup.findAll('a', {'class': 'series_preview'})
        error_text = 'Error: Manga \'{0}\' does not exist'.format(manga_name)
        error_text += '\nDid you meant one of the following?\n  * '
        error_text += '\n  * '.join([manga.text for manga in results][:10])
        sys.exit(error_text)
    warning = soup.find('div', {'class': 'warning'})
    if warning and 'licensed' in warning.text:
        sys.exit('Error: ' + warning.text)
    chapters = OrderedDict()
    links = soup.findAll('a', {'class': 'tips'})
    if(len(links) == 0):
        sys.exit('Error: Manga either does not exist or has no chapters')
    replace_manga_name = re.compile(re.escape(manga_name.replace('_', ' ')),
                                    re.IGNORECASE)

    for link in links:
        chapters[float(replace_manga_name.sub('', link.text).strip())] = link['href']

    ordered_chapters = OrderedDict(sorted(chapters.items()))

    return ordered_chapters

def get_page_numbers(soup):
    """Return the list of page numbers from the parsed page"""
    raw = soup.findAll('select', {'class': 'm'})[0]
    return (html['value'] for html in raw.findAll('option'))

def get_chapter_image_urls(url_fragment):
    """Find all image urls of a chapter and return them"""
    print('Getting chapter urls')
    url_fragment = os.path.dirname(url_fragment) + '/'
    chapter_url = url_fragment
    chapter = get_page_soup(chapter_url)
    pages = get_page_numbers(chapter)
    image_urls = []
    print('Getting image urls...')
    for page in pages:
        if page != "0":
            print('url_fragment: {0}'.format(url_fragment))
            print('page: {0}'.format(page))
            print('Getting image url from {0}{1}.html'.format(url_fragment, page))
            page_soup = get_page_soup(chapter_url + page + '.html')
            images = page_soup.findAll('img', {'id': 'image'})
            if images:
                image_urls.append(images[0]['src'])
            time.sleep(0.05)
    return image_urls

def get_volume_info(url_fragment):
    """Parse the url fragment and return the chapter number."""
    return url_fragment.rsplit("/")[5:-1]

def download_urls(image_urls, manga_name, volume, chapter):
    """Download all images from a list"""

    download_dir = '{0}/{1}/'.format(manga_name, volume)
    if os.path.exists(download_dir):
        shutil.rmtree(download_dir)
    os.makedirs(download_dir)
    for i, url in enumerate(image_urls):
        filename = '.\\{0}\\{1}\\{2}p{3:03}.jpg'.format(manga_name, volume, chapter, i)

        print('Downloading {0} to {1}'.format(url, filename))
        for i in range(15):
            try:
                r = requests.get(url, stream=True, headers={'User-agent': 'Mozilla/5.0'})
                if r.status_code == 200:
                    with open(filename, 'wb') as f:
                        r.raw.decode_content = True
                        shutil.copyfileobj(r.raw, f)
            except urllib.error.HTTPError as http_err:
                print ('HTTP error ', http_err.code, ": ", http_err.reason)
                if http_err.code == 404:
                    print (ulr + "does not exist")
                    break
                time.sleep(2)
            except urllib.error.ContentTooShortError:
                print ('The image has been retrieve only partially.')
            except:
                print ('Unknown error')
                time.sleep(2)
            else:
                break
            if i == 14:
                exit("Could not download " + ulr)

def make_cbz(dirname):
    """Create CBZ files for all JPEG image files in a directory."""
    zipname = dirname + '.cbz'
    images = sorted(glob.glob(os.path.abspath(dirname) + '/*.jpg'))
    with closing(ZipFile(zipname, 'w')) as zipfile:
        for filename in images:
            print('writing {0} to {1}'.format(filename, zipname))
            zipfile.write(filename)

def download_manga(manga_name, range_start=1, range_end=None, b_make_cbz=False, remove=False):
    """Download a range of a chapters"""

    chapter_urls = get_chapter_urls(manga_name)

    if range_end == None : range_end = max(chapter_urls.keys())

    for chapter, url in filterfalse (lambda chapter_url:
                                     chapter_url[0] < range_start
                                     or chapter_url[0] > range_end,
                                     chapter_urls.items()):
        volume, chapter = get_volume_info(url)

        print('=================================================')
        print('Volume: {0}, Chapter: {1}'.format(volume, chapter))
        print('=================================================')
        image_urls = get_chapter_image_urls(url)
        download_urls(image_urls, manga_name, volume, chapter)
        download_dir = './{0}/{1}'.format(manga_name, volume)
        if b_make_cbz is True:
            make_cbz(download_dir)
            if remove is True: shutil.rmtree(download_dir)

def main():
    parser = argparse.ArgumentParser(description='Manga Fox Downloader')

    parser.add_argument('--manga', '-m',
                        required=True,
                        action='store',
                        help='Manga to download')

    parser.add_argument('--start', '-s',
                        action='store',
                        type=int,
                        default=1,
                        help='Chapter to start downloading from')

    parser.add_argument('--end', '-e',
                        action='store',
                        type=int,
                        default=None,
                        help='Chapter to end downloading to')

    parser.add_argument('--cbz', '-c',
                        action="store_true",
                        default=False,
                        help="Create cbz archive after download")

    parser.add_argument('--remove', '-r',
                        action="store_true",
                        default=False,
                        help="Remove image files after the creation of a cbz archive")

    args = parser.parse_args()

    print('Getting chapter of ', args.manga, 'from ', args.start, ' to ', args.end)

    download_manga(args.manga, args.start, args.end, args.cbz, args.remove)

if __name__ == "__main__":
    main()
