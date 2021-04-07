import requests
import re
from bs4 import BeautifulSoup
import sys
import os


# Original from Github

class Configuration:

    def __init__(self):
        # Шаблоны предварительной обработки
        self.pre_processing = [
            # Удаляем теги scripts
            r'<(script).*?</\1>(?s)',
            # Удаляем теги styles
            r'<(style).*?</\1>(?s)',
            # Удаляем теги meta
            r'<(meta).*?>',
            # Удаляем теги ul's (опционально)
            '<(ul).*?</\1>(?s)',
            # Удаляем теги navigation
            r'<(nav).*?</\1>(?s)',
            # Удаляем теги footer
            r'<(footer).*?</\1>(?s)',
            # Удаляем теги header
            r'<(header).*?</\1>(?s)',
            # Удаляем теги forms
            r'<(form).*?</\1>(?s)'
        ]

        # Коэффциент обрезки
        self.COEFF = 0.5

        # Усиленный поиск по тегу <p>
        self.FORCED = True

        # Ширина строки при форматировании
        self.MAX_LENGTH = 80


class Parser(Configuration):
    """
    Этот класс отвечает за парсинг и подготовку данных HTML.
    Он обертывает объект в bs4.
    -------------
    Публичные методы:
    main_content(density, soup, force) -> главная функция
    get_html(url) -> выдает "сырой" html-объект после обработки

    Защищенные методы:
    preprocess(html) -> обработка html-объекта
    calc_depth(node) -> вычисление глубины узла для каждого уровня дерева
    calc_density(nodes) -> сохранение значений глубины узлов в словаре
    """

    def get_html(self, url):
        """
        [Публичный]
        Функция создает запрос по url и подготавливает данные
        -----------
        inputs:
           url: string

        returns:
           html: string
        """

        # запрос и создание html-объекта
        with requests.Session() as session:
            session.headers = {'User-Agent': 'Mozilla/5.0'}
            request = session.get(url)
            html = self._prepocess(request.text)

        return html

    def _prepocess(self, html):
        """
        [Защищенный]
        Эта функция используется для предварительной обработки данных.
        Использует механизм regexp для подготовки html.
        ------------
           inputs:
              html: string

           returns:
              html: string
        """

        # использование шаблонов
        patterns = [re.compile(p) for p in self.pre_processing]

        for pattern in patterns:
            html = re.subn(pattern, '', html)[0]

        return html

    def _calc_depth(self, node):
        """
        [Защищенный]
        Эта функция вычисляет максимальную глубину узлов
        -----------
           inputs:
              node: bs4 node

           returns:
              depth: list or null
        """

        # глубина
        if hasattr(node, "contents") and node.contents:
            return max([self._calc_depth(child) for child in node.contents]) + 1
        else:
            return 0

    def _calc_density(self, nodes):
        """
        [Защищенный]
        Эта функция вычисляет глубину каждого узла
        -------------
            inputs:
            nodes: bs4 node

            :returns
            node_density: dict
        """

        node_density = {}

        # основной цикл
        for node in nodes:
            density = self._calc_depth(node)
            node_density.update({node: density})

        return node_density

    def main_content(self, density=None, soup=None, forced=False):
        """
        [Публичный]
        Основная функция класса. Алгоритм рекурсивно перебирает все узлы и удаляет те ветви,
        которые меньше определенного коэффициента
         --------------
         inputs:
            density: dict -> значение глубины
            soup: bs4 object -> BeatifullSoup-объект
            forced: bool -> усиленный поиск по тегу <p>

        returns:
            soup: bs4 object -> обработанный BeatifullSoup-объект
        """

        coef = self.COEFF

        if density is None:
            # получение потомков (1)
            children = soup.find_all(True, recursive=False)
            # вычисление глубины (2)
            density = self._calc_density(children)
            self.main_content(density=density, soup=soup, forced=forced)

        for node in density.keys():

            # повтор пунктов (1) и (2)
            childs = node.find_all(True, recursive=False)
            density = self._calc_density(childs)

            avg = sum(density.values()) * coef

            # избегаем ошибки "dict size changed"
            keys = list(density.keys())

            # основной цикл
            for node in keys:

                # удаляем теги <p> и <h>
                if node.name == 'p' or node.name == 'h1' or node.name == 'h2':
                    continue

                if node.h1:
                    continue

                # не удаляем тег <p> если он содержит хотя бы 3 потомка
                if forced:
                    if len(node.find_all('p')) > 3:
                        continue

                # удаляем узел (возможная реклама)
                if density[node] < avg:
                    node.decompose()

            # рекурсия
            for node in density.keys():
                self.main_content(density, soup=soup, forced=forced)

        return soup


class Formatter(Configuration):
    """
    Это класс подготавливает тектс и записывает его в файл
    ----------
    Публичные методы:
    prepare_text(soup, max_length) -> подготовка текста
    write_file(text) -> запись в файл

    Защищенные методы:
    domain_name(url) -> извлечение доменного имени
    get_url(urls, domain) -> вставка ссылок в []
    add_urls(text, prepared_urls) -> вставка ссылок в текст
    """

    def __init__(self, domain):
        super().__init__()
        self.domain = domain

    def _domain_name(self, url):
        """
        [Защищенный]
        Эта функция извлекает доменное имя по шаблону
          -----------
          inputs:
              url: string

          returns:
              url: string
        """
        return re.match(r'http(s)?://', url).group() + url.split("//")[-1].split("/")[0]

    def _get_urls(self, urls, domain):
        """
        [Защищенный]
        Эта функция извлекает ссылки
        ---------
        inputs:
            urls: list -> список ссылок со страницы
            domain: string

        returns:
           r_urls: dict -> готовые ссылки
        """

        r_urls = {}

        # доменное имя
        domain = self._domain_name(domain)

        # вставляем в квадратные скобки
        for url in urls:
            if ("http" or "htpps") not in url['href']:
                href = '[' + domain + url['href'] + ']'
                r_urls.update({href: url.text})
            else:
                href = '[' + url['href'] + ']'
                r_urls.update({href: url.text})

        return r_urls

    def _add_urls(self, text, prepared_urls):
        """
        [Защищенный]
        Эта функция вставляет подготовленные ссылки в текст
        -----------
        inputs:
           text: string -> html-объект
           prepared_urls: dict -> извлеченные ссылки

        returns:
           text: string -> текст с ссылками
        """

        for url in prepared_urls.keys():
            text = re.sub(prepared_urls[url], prepared_urls[url] + ' ' + url, text)
        return text

    def prepare_text(self, soup):
        """
        [PUBLIC]
        Эта функция обрабатывает текст, удаляя лишние отступы и вкладки.
        После этого делает строки заданной длины.
        -----------
           inputs:
              soup: bs4 object -> BeatifullSoup-объект.

           returns:
              new_string: string -> готовый текст
        """

        # получаем все абзацы и ссылки
        paragr = soup.find_all('p')
        urls = soup.find_all('a')

        # преобразуем текст
        string = soup.text
        string = string.replace('\n', '')
        string = string.strip()
        string = string.replace(r'\s+', ' ')

        # разделяем абзацы
        for p in paragr:
            if p.text == '':
                continue
            string = string.replace(p.text.strip(), '\n' + p.text.strip() + '\n')

        # вставляем ссылки
        prepared_urls = self._get_urls(urls, self.domain)
        text_with_urls = self._add_urls(string, prepared_urls)

        # основной шаблон
        sp2 = re.findall(r"(\[(https?://[^\s]+)\]|[\w]+|[\s.,!?;\()-])", text_with_urls)

        length = 1
        new_string = ''

        # преобразуем текст по заданной длине строки
        for word in sp2:
            w = word[0]
            if length == 1:
                w = word[0].lstrip()
            length += len(word[0])

            if w == '\n':
                new_string += '\n'
                length = 1

            if length > self.MAX_LENGTH:
                new_string += '\n'
                new_string += w
                length = len(w) + 1

            elif length == self.MAX_LENGTH:
                new_string += w + '\n'
                length = 1

            else:
                new_string += w

        return new_string.replace('\n\n\n', '\n')

    def write_file(self, text):
        """
        [Публичный]
        Эта функция создает директорию и записывает тектст в файл
        -------------
        inputs:
           text: string -> текст
        """

        # путь к файлу
        file_name = re.sub(r"http(s)?://(www\.)?", '', self.domain)
        file_name = re.sub(r'.(s)?html|/$', '', file_name)

        dir = os.path.dirname(file_name)

        # создаем директорию, если она еще не существует
        if not os.path.exists(dir):
            os.makedirs(dir)

        # запись в файл
        with open(file_name + '.txt', 'w') as f:
            f.write(text)


# Запуск программы

# ожидание ввода
if len(sys.argv) > 1:
    url = sys.argv[1]
else:
    url = input('Please, enter url: ')

# создаем экземпляр парсера
parser = Parser()

# получаем html-объект
html = parser.get_html(url)

# получаем целевой объект для обрабоки в виде xml
soup = BeautifulSoup(html, 'lxml')

# обработка
clean_soup = parser.main_content(soup=soup, forced=True)

# создаем экземпляр обработчика текста
formatter = Formatter(domain=url)

# чистим наш текст
clean_text = formatter.prepare_text(clean_soup)

# записываем в файл
formatter.write_file(clean_text)
