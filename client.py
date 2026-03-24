import socket
import sys
import argparse
import time
import signal


class LogClient:
    """Клиент для отправки логов на сервер"""

    def __init__(self, host='localhost', port=8888):
        self.host = host
        self.port = port
        self.socket = None
        self.connected = False

    def connect(self):
        """Подключение к серверу"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            self.connected = True
            return True
        except Exception as e:
            print(f"Ошибка подключения к серверу {self.host}:{self.port}: {e}")
            return False

    def send_log(self, level, message, tag=None):
        """Отправка лога на сервер"""
        if not self.connected:
            if not self.connect():
                return False

        try:
            if tag:
                log_data = f"LOG {level} {tag} {message}"
            else:
                log_data = f"LOG {level} {message}"

            self.socket.send(log_data.encode('utf-8'))

            # Получение ответа
            response = self.socket.recv(1024).decode('utf-8').strip()
            print(f"Ответ сервера: {response}")
            return True

        except (socket.error, ConnectionResetError) as e:
            print(f"Ошибка отправки лога: {e}")
            self.connected = False
            return False
        except Exception as e:
            print(f"Неожиданная ошибка: {e}")
            return False

    def ping(self):
        """Проверка соединения с сервером"""
        if not self.connected:
            if not self.connect():
                return False

        try:
            self.socket.send("PING".encode('utf-8'))
            response = self.socket.recv(1024).decode('utf-8').strip()
            print(f"Ping ответ: {response}")
            return response == "PONG"

        except socket.error:
            self.connected = False
            print("Ошибка при отправке PING")
            return False

    def get_stats(self):
        """Получение статистики сервера"""
        if not self.connected:
            if not self.connect():
                return

        try:
            self.socket.send("STATS".encode('utf-8'))
            response = self.socket.recv(4096).decode('utf-8').strip()
            print(f"Статистика сервера:\n{response}")

        except socket.error:
            self.connected = False
            print("Ошибка при получении статистики")

    def disconnect(self):
        """Отключение от сервера"""
        if self.connected:
            try:
                self.socket.send("QUIT".encode('utf-8'))
                response = self.socket.recv(1024).decode('utf-8')
                print(f"Отключение: {response}")
            except:
                pass
            finally:
                self.socket.close()
                self.connected = False

    def interactive_mode(self):
        """Интерактивный режим работы"""
        print("=" * 60)
        print("Клиент логов - интерактивный режим")
        print("=" * 60)
        print("Доступные команды:")
        print("  log <LEVEL> [TAG] <MESSAGE> - отправить лог (LEVEL: INFO, WARN, ERROR)")
        print("  ping - проверить соединение с сервером")
        print("  stats - получить статистику сервера")
        print("  help - показать эту справку")
        print("  quit/exit - выйти")
        print("=" * 60)

        while True:
            try:
                user_input = input("\n> ").strip()
                if not user_input:
                    continue

                if user_input.lower() in ['quit', 'exit']:
                    break
                elif user_input.lower() == 'help':
                    print("Команды:")
                    print("  log INFO [TAG] сообщение - отправить информационное сообщение")
                    print("  log WARN [TAG] сообщение - отправить предупреждение")
                    print("  log ERROR [TAG] сообщение - отправить ошибку")
                    print("  ping - проверить соединение")
                    print("  stats - статистика сервера")
                    print("  quit - выход")
                elif user_input.lower() == 'ping':
                    self.ping()
                elif user_input.lower() == 'stats':
                    self.get_stats()
                elif user_input.lower().startswith('log '):
                    parts = user_input[4:].split()
                    if len(parts) < 2:
                        print("Использование: log <LEVEL> [TAG] <MESSAGE>")
                        continue

                    level = parts[0].upper()
                    if level not in ['INFO', 'WARN', 'ERROR']:
                        print(f"Некорректный уровень лога: {level}. Используйте: INFO, WARN, ERROR")
                        continue

                    if len(parts) >= 3 and not parts[1].upper() in ['INFO', 'WARN', 'ERROR']:
                        # Есть тег
                        tag = parts[1]
                        message = ' '.join(parts[2:])
                        self.send_log(level, message, tag)
                    else:
                        # Нет тега
                        message = ' '.join(parts[1:])
                        self.send_log(level, message)
                else:
                    print("Неизвестная команда. Используйте 'help' для справки.")

            except KeyboardInterrupt:
                print("\nПрерывание работы...")
                break
            except EOFError:
                break
            except Exception as e:
                print(f"Ошибка: {e}")

    def batch_mode(self, level, tag, message):
        """Пакетный режим отправки одного лога"""
        if self.send_log(level, message, tag):
            return 0
        return 1


def main():
    """Точка входа для клиента"""
    parser = argparse.ArgumentParser(description='Клиент логов')
    parser.add_argument('--host', default='localhost', help='IP адрес сервера')
    parser.add_argument('--port', type=int, default=8888, help='Порт сервера')
    parser.add_argument('--level', choices=['INFO', 'WARN', 'ERROR'], help='Уровень лога')
    parser.add_argument('--tag', help='Тег лога')
    parser.add_argument('message', nargs='?', help='Сообщение лога')

    args = parser.parse_args()

    client = LogClient(args.host, args.port)

    # Обработчик сигналов для graceful shutdown
    def signal_handler(signum, frame):
        print("\nПолучен сигнал завершения...")
        client.disconnect()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Определение режима работы
    if args.level and args.message:
        # Пакетный режим
        exit_code = client.batch_mode(args.level, args.tag, args.message)
        client.disconnect()
        sys.exit(exit_code)
    else:
        # Интерактивный режим
        if client.connect():
            client.interactive_mode()
            client.disconnect()
        else:
            print("Не удалось подключиться к серверу")
            sys.exit(1)


if __name__ == '__main__':
    main()