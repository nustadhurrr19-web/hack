<?php
header("Access-Control-Allow-Origin: *");
header("Access-Control-Allow-Methods: GET");
header("Access-Control-Allow-Headers: Content-Type");
header("Content-Type: application/json");

$apiUrl = "https://harshpredictor.site/api/api.php";

// Basic protection
$context = stream_context_create([
    "http" => [
        "method" => "GET",
        "timeout" => 5
    ]
]);

$response = @file_get_contents($apiUrl, false, $context);

if ($response === FALSE) {
    echo json_encode([
        "error" => true,
        "message" => "API fetch failed"
    ]);
    exit;
}

echo $response;
