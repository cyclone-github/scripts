<?php
// script by cyclone to check plaintexts against Umbraco HMACSHA256 hashes
// while slow, script supports multi-gigabyte wordlists
// coding this in php was an experiment, so don't cry about how slow it runs
// $hash_file must be formatted as: "salt==:hash=" (without quotes), sanity check will skip hashes which don't contain ":"
// requires php & php-mbstring to be installed (ex: sudo apt install php8.2 php8.2-php-mbstring -y)
// tested with php7.4 & php8.2
// version 2022-12-14.1200

echo "\e[H\e[J"; // clear screen
$t=time(); // define time

$start_time = microtime(true);
$count = 0;
$count_lines = 0;
$time = 0;
$wordlist = "wordlist/cyclone_hk_v2.txt"; // point to local wordlist file <---------------------------------------------------- ## EDIT ##
$hash_file = file('tmp_hash.txt', FILE_SKIP_EMPTY_LINES|FILE_IGNORE_NEW_LINES); // point to 'salt==:hash=' file <-------------- ## EDIT ##

echo "\n#############################################\n";
echo "# Cyclone's Umbraco HMACSHA256 Hash Cracker #\n";
echo "#############################################\n";
echo "\nStarting Search...\n";
echo "This may take a while with many hashes and/or large wordlists.\n";

// optimized getLines wordcount (works with large wordlists)
function getLines($file) {
    $f = fopen($file, 'rb');
    $lines = 0; $buffer = '';
    while (!feof($f)) {
        $buffer = fread($f, 8192);
        $lines += substr_count($buffer, "\n");
    }
    fclose($f);
    if (strlen($buffer) > 0 && $buffer[-1] != "\n") {
        ++$lines;
    }
    return $lines;
}

// start main cracking loop
if ($file = fopen($wordlist, "r")) {
    echo "\nCounting lines in $wordlist...\n";
    $lines = getLines($wordlist);
    echo "Total lines: $lines\n";
    while(!feof($file)) {
        $line_raw = fgets($file);
        $line = trim($line_raw); // trim off whitespace from $line_raw
        $line_pass_utf16le = mb_convert_encoding($line, "UTF-16LE"); // convert $line to UTF-16LE
        $count_lines++; // count lines processed
        foreach($hash_file as $hash_line) {
            if (strpos($hash_line, ':') === false) {
                continue 1;
            } else {
                $hash_array = preg_split("/\:/", $hash_line); // split $hash_file into salt / hash arrays
                $salt_split = trim($hash_array[0]); // salt array
                $hash_split = trim($hash_array[1]); // hash array
                $input = $salt_split . $hash_split; // $input salt/hash for comparison with $output
                $salt_proper = base64_decode($salt_split) . base64_decode($salt_split) . base64_decode($salt_split) . base64_decode($salt_split); // process salt
                $dgst = hash_hmac("sha256", $line_pass_utf16le, $salt_proper, true); // hmac256
                $output = $salt_split . base64_encode($dgst); // compare $output with $input to see if we've cracked the hash with $line (password)
                if (time()-$time >= 60) { // show words / percentage searched every 60 seconds
                    $percent = ($count_lines / $lines) * 100;
                    echo "\nProgress: " . $count_lines . " of " . $lines . ", " . number_format((float)$percent, 2, '.', '') . "%" . ", Hashes found: " . $count;
                    $time = time();
                }
                if ($output == $input){ // display cracked hashes
                    echo "\n##################################################################################\n";
                    echo "Password: $line\n";
                    echo "salt==hash: ";
                    echo $salt_split . ":" . base64_encode($dgst);
                    echo "\n";
                    $count++; // count +1 hashes found
                    echo "\nHashes found: " . $count;
                    echo "\n##################################################################################\n";
                }
            }
        }
    }
    fclose($file); // close wordlist
}
echo "\nFinished searching.\n";
echo "\nHashes found: " . $count . "\n\n"; // show how many hashes were found
$end_time = microtime(true); // end clock time in seconds
$execution_time = ($end_time - $start_time); // calculate script execution time
echo "Script runtime: " . number_format((float)$execution_time, 3, '.', '') . " seconds\n"; // show script execution time
?>
