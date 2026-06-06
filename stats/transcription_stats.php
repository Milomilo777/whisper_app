<?php
/**
 * Whisper Project — transcription usage stats endpoint (P4-4).
 *
 * A minimal GET/POST recorder. POST `form_submitted=1` (plus the fields
 * below) to insert one usage row; a bare GET shows the SQLite version and a
 * tiny form (handy for a manual smoke test). Callable from the desktop app
 * via python `requests`/`urllib` (application/x-www-form-urlencoded).
 *
 * It records, per transcription:
 *   - client IP            (REMOTE_ADDR of the request)
 *   - country_name         (extracted from the geoip JSON below)
 *   - ip_location_json     (the FULL geoip JSON for that IP)
 *   - file_name            (basename only — the app strips the path)
 *   - model, language
 *   - audio_duration       (seconds)
 *   - transcription_time   (seconds of AI compute)
 *   - status               (finished / error / cancelled / ...)
 *   - word_count           (total words in the transcript)
 *
 * GeoIP is fetched server-side from:
 *   https://smch.ir/stats/geoip/index.php?ip={ip}
 * whose response looks like:
 *   {"status":"success","country":"Switzerland","countryCode":"CH",...}
 *
 * Connection/driver style mirrors the maintainer's other PDO-SQLite stats
 * pages (a plain `new PDO("sqlite:...")`), but the code here is purpose-built
 * and minimal — it deliberately does NOT reuse robot-stats.php.
 */

error_reporting(E_ALL & ~E_NOTICE & ~E_WARNING);

if (function_exists('opcache_invalidate')) {
    opcache_invalidate(__FILE__, true);
}

date_default_timezone_set('Europe/Paris');

// --- database ---------------------------------------------------------------
// One file next to this script. PDO SQLite driver, same as the sibling stats
// pages. The table is created on first run (idempotent).
$db = new PDO('sqlite:' . __DIR__ . '/transcription_stats.db');
$db->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);

$db->exec(
    'CREATE TABLE IF NOT EXISTS transcription_stats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        server_time TEXT,
        client_ip TEXT,
        country_name TEXT,
        ip_location_json TEXT,
        file_name TEXT,
        model TEXT,
        language TEXT,
        audio_duration REAL,
        transcription_time REAL,
        word_count INTEGER,
        status TEXT
    )'
);

// --- geoip lookup -----------------------------------------------------------
/**
 * Fetch the geoip JSON for $ip and return [country_name, raw_json_string].
 * Best-effort: on any failure returns ['', ''] so a recorded row never blocks
 * on the lookup.
 */
function lookup_geoip($ip) {
    $country = '';
    $raw = '';
    if ($ip === '') {
        return array($country, $raw);
    }
    $url = 'https://smch.ir/stats/geoip/index.php?ip=' . urlencode($ip);
    try {
        $ctx = stream_context_create(array(
            'http' => array('timeout' => 4),
            'ssl'  => array('verify_peer' => false, 'verify_peer_name' => false),
        ));
        $raw = @file_get_contents($url, false, $ctx);
        if ($raw === false) {
            $raw = '';
        }
        if ($raw !== '') {
            $json = json_decode($raw);
            if (is_object($json) && isset($json->status) && $json->status === 'success'
                && isset($json->country)) {
                $country = (string) $json->country;
            }
        }
    } catch (Exception $e) {
        // Swallow — geoip is decoration, not a requirement.
        $country = '';
    }
    return array($country, $raw);
}

// --- record a row -----------------------------------------------------------
$recorded = false;
if (isset($_POST['form_submitted'])) {
    $client_ip = isset($_SERVER['REMOTE_ADDR']) ? $_SERVER['REMOTE_ADDR'] : '';
    list($country_name, $ip_location_json) = lookup_geoip($client_ip);

    $file_name = isset($_POST['file_name']) ? basename((string) $_POST['file_name']) : '';
    $model = isset($_POST['model']) ? (string) $_POST['model'] : '';
    $language = isset($_POST['language']) ? (string) $_POST['language'] : '';
    $audio_duration = isset($_POST['audio_duration']) ? (float) $_POST['audio_duration'] : 0.0;
    $transcription_time = isset($_POST['transcription_time']) ? (float) $_POST['transcription_time'] : 0.0;
    $word_count = isset($_POST['word_count']) ? (int) $_POST['word_count'] : 0;
    $status = isset($_POST['status']) ? (string) $_POST['status'] : '';
    $server_time = date(DATE_RFC3339);

    $stmt = $db->prepare(
        'INSERT INTO transcription_stats
            (server_time, client_ip, country_name, ip_location_json,
             file_name, model, language, audio_duration, transcription_time,
             word_count, status)
         VALUES
            (:server_time, :client_ip, :country_name, :ip_location_json,
             :file_name, :model, :language, :audio_duration, :transcription_time,
             :word_count, :status)'
    );
    $stmt->bindValue(':server_time', $server_time);
    $stmt->bindValue(':client_ip', $client_ip);
    $stmt->bindValue(':country_name', $country_name);
    $stmt->bindValue(':ip_location_json', $ip_location_json);
    $stmt->bindValue(':file_name', $file_name);
    $stmt->bindValue(':model', $model);
    $stmt->bindValue(':language', $language);
    $stmt->bindValue(':audio_duration', $audio_duration);
    $stmt->bindValue(':transcription_time', $transcription_time);
    $stmt->bindValue(':word_count', $word_count, PDO::PARAM_INT);
    $stmt->bindValue(':status', $status);
    $stmt->execute();
    $recorded = true;
}

// --- response ---------------------------------------------------------------
// Plain text so the python client can read a one-word confirmation cheaply.
header('Content-Type: text/plain; charset=UTF-8');

$ver = SQLite3::version();
if ($recorded) {
    echo "OK\n";
} else {
    echo "Whisper Project transcription stats endpoint.\n";
    echo "SQLite " . $ver['versionString'] . "\n";
    echo "POST form_submitted=1 with: file_name, model, language, ";
    echo "audio_duration, transcription_time, word_count, status\n";
}
