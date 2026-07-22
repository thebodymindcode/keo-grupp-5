<?php
/**
 * Приём заявок с форм сайта keogroup.ru и отправка на почту компании.
 * Работает на хостинге Beget (PHP + локальная почта). Стороннего сервиса не нужно.
 * Формы шлют POST (FormData): name, phone, service, task, _subject, _gotcha (honeypot).
 */

$TO   = 'info@keogroup.ru, 8111706@gmail.com';  // куда падают заявки (можно несколько через запятую)
$FROM = 'info@keogroup.ru';          // от кого (ящик существует на домене, проходит SPF)
$LOG  = __DIR__ . '/zayavki.log';    // резервная запись (закрыта в .htaccess)

header('Content-Type: application/json; charset=UTF-8');

function fail($code, $msg) {
    http_response_code($code);
    echo json_encode(['ok' => false, 'error' => $msg], JSON_UNESCAPED_UNICODE);
    exit;
}
function done() {
    http_response_code(200);
    echo json_encode(['ok' => true], JSON_UNESCAPED_UNICODE);
    exit;
}

if ($_SERVER['REQUEST_METHOD'] !== 'POST') fail(405, 'Только POST');

// Ловушка для ботов: заполнено скрытое поле — тихо отвечаем «ок», письмо не шлём.
if (!empty($_POST['_gotcha'])) done();

$clean = function ($v) { return trim(preg_replace('/[\r\n]+/', ' ', (string)$v)); };

$name    = $clean($_POST['name']    ?? '');
$phone   = $clean($_POST['phone']   ?? '');
$service = $clean($_POST['service'] ?? '');
$task    = trim((string)($_POST['task'] ?? ''));
$subject = $clean($_POST['_subject'] ?? 'Заявка с сайта KEO GROUP');

$digits = preg_replace('/\D/', '', $phone);
if (mb_strlen($name) < 2)        fail(422, 'Впишите имя');
if (strlen($digits) < 11)        fail(422, 'Проверьте телефон');

// Тело письма
$lines = [];
$lines[] = 'Новая заявка с сайта keogroup.ru';
$lines[] = str_repeat('-', 40);
$lines[] = 'Имя:      ' . $name;
$lines[] = 'Телефон:  ' . $phone;
if ($service !== '') $lines[] = 'Услуга:   ' . $service;
if ($task !== '')    $lines[] = "Задача:\n" . $task;
$lines[] = str_repeat('-', 40);
$lines[] = 'Страница: ' . ($_SERVER['HTTP_REFERER'] ?? '-');
$lines[] = 'Время:    ' . date('d.m.Y H:i:s');
$lines[] = 'IP:       ' . ($_SERVER['REMOTE_ADDR'] ?? '-');
$body = implode("\n", $lines) . "\n";

// Резервная запись в лог (чтобы заявка не потерялась, даже если почта сбойнёт)
@file_put_contents($LOG, "\n=== " . date('d.m.Y H:i:s') . " ===\n" . $body, FILE_APPEND | LOCK_EX);

// Кодируем тему в UTF-8 для корректного отображения кириллицы
$fullSubject = $subject . ($service !== '' ? ' — ' . $service : '');
$encSubject  = '=?UTF-8?B?' . base64_encode($fullSubject) . '?=';

$headers  = 'From: KEO GROUP <' . $FROM . ">\r\n";
$headers .= 'Reply-To: ' . $FROM . "\r\n";
$headers .= "MIME-Version: 1.0\r\n";
$headers .= "Content-Type: text/plain; charset=UTF-8\r\n";
$headers .= "Content-Transfer-Encoding: 8bit\r\n";
$headers .= 'X-Mailer: keogroup-site';

$sent = @mail($TO, $encSubject, $body, $headers, '-f' . $FROM);

if ($sent) done();
// Даже если mail() вернул false, заявка уже в логе. Не пугаем клиента, но помечаем ошибку сервера.
fail(500, 'Письмо не отправилось, но заявка сохранена. Мы свяжемся с вами.');
