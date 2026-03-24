import socket
import threading
import signal
import sys
import os
import time
from datetime import datetime
import logging


class LogServer:
    """Сервер для приема и сохранения логов"""

    def __init__(self, host='localhost', port=8888, log_file='server_logs.txt'):
        self.host = host
        self.port = port
        self.log_file = log_file
        self.server_socket = None
        self.clients = {}
        self.running = True
        self.lock = threading.Lock()

        # Настройка логирования сервера
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('server_system.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

        # Создание директории для логов если нужно
        self._ensure_log_directory()

    def _ensure_log_directory(self):
        """Создание директории для файла логов"""
        log_dir = os.path.dirname(self.log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)

    def _write_log_to_file(self, log_entry):
        """Запись лога в файл"""
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(log_entry + '\n')
        except Exception as e:
            self.logger.error(f"Ошибка записи в файл логов: {e}")

    def _parse_log_message(self, message):
        """Разбор сообщения лога"""
        parts = message.strip().split(' ', 2)
        if len(parts) < 2:
            return None, None, None

        level = parts[0].upper()
        if len(parts) == 2:
            content = parts[1]
            tag = None
        else:
            tag = parts[1]
            content = parts[2]

        return level, content, tag

    def handle_client(self, client_socket, client_address):
        """Обработка подключения клиента"""
        client_id = f"{client_address[0]}:{client_address[1]}"

        with self.lock:
            self.clients[client_id] = client_socket
        self.logger.info(f"Клиент подключен: {client_id}")

        try:
            while self.running:
                # Получение данных от клиента
                data = client_socket.recv(4096).decode('utf-8').strip()
                if not data:
                    break

                # Разбор команды
                if data.startswith('LOG'):
                    # Формат: LOG <LEVEL> [TAG] <MESSAGE>
                    log_data = data[3:].strip()
                    level, content, tag = self._parse_log_message(log_data)

                    if level and content:
                        # Добавление метки времени
                        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        log_entry = f"[{timestamp}] [{level}]"
                        if tag:
                            log_entry += f" [{tag}]"
                        log_entry += f": {content}"

                        # Запись в файл
                        self._write_log_to_file(log_entry)
                        self.logger.info(f"Записан лог от {client_id}: {level} - {content[:50]}")

                        # Отправка подтверждения клиенту
                        response = "OK Log saved\n"
                        client_socket.send(response.encode('utf-8'))
                    else:
                        response = "ERROR Invalid log format. Use: LOG <LEVEL> [TAG] <MESSAGE>\n"
                        client_socket.send(response.encode('utf-8'))

                elif data == 'PING':
                    response = "PONG\n"
                    client_socket.send(response.encode('utf-8'))

                elif data == 'STATS':
                    with self.lock:
                        stats = f"Connected clients: {len(self.clients)}\n"
                    response = f"OK\n{stats}"
                    client_socket.send(response.encode('utf-8'))

                elif data == 'QUIT':
                    response = "OK Goodbye\n"
                    client_socket.send(response.encode('utf-8'))
                    break

                else:
                    response = "ERROR Unknown command. Commands: LOG, PING, STATS, QUIT\n"
                    client_socket.send(response.encode('utf-8'))

        except ConnectionResetError:
            self.logger.warning(f"Клиент {client_id} аварийно отключился")
        except Exception as e:
            self.logger.error(f"Ошибка при обработке клиента {client_id}: {e}")
        finally:
            with self.lock:
                if client_id in self.clients:
                    del self.clients[client_id]
            client_socket.close()
            self.logger.info(f"Клиент отключен: {client_id}")

    def start(self):
        """Запуск сервера"""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)

            self.logger.info(f"Сервер логов запущен на {self.host}:{self.port}")
            self.logger.info(f"Логи сохраняются в файл: {self.log_file}")

            # Установка обработчиков сигналов
            signal.signal(signal.SIGINT, self.signal_handler)
            signal.signal(signal.SIGTERM, self.signal_handler)

            while self.running:
                try:
                    self.server_socket.settimeout(1.0)
                    client_socket, client_address = self.server_socket.accept()
                    client_thread = threading.Thread(
                        target=self.handle_client,
                        args=(client_socket, client_address),
                        daemon=True
                    )
                    client_thread.start()
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        self.logger.error(f"Ошибка при принятии соединения: {e}")

        except Exception as e:
            self.logger.error(f"Ошибка запуска сервера: {e}")
            sys.exit(1)

    def signal_handler(self, signum, frame):
        """Обработчик сигналов для graceful shutdown"""
        self.logger.info(f"Получен сигнал {signum}, завершение работы...")
        self.stop()

    def stop(self):
        """Остановка сервера"""
        self.running = False

        # Закрытие всех клиентских соединений
        with self.lock:
            for client_id, client_socket in self.clients.items():
                try:
                    client_socket.close()
                except:
                    pass
            self.clients.clear()

        # Закрытие серверного сокета
        if self.server_socket:
            self.server_socket.close()

        self.logger.info("Сервер остановлен")


def main():
    """Точка входа для сервера"""
    import argparse

    parser = argparse.ArgumentParser(description='Сервер логов')
    parser.add_argument('--host', default='localhost', help='IP адрес сервера')
    parser.add_argument('--port', type=int, default=8888, help='Порт сервера')
    parser.add_argument('--log-file', default='server_logs.txt', help='Файл для сохранения логов')

    args = parser.parse_args()

    server = LogServer(args.host, args.port, args.log_file)
    server.start()


if __name__ == '__main__':
    main()