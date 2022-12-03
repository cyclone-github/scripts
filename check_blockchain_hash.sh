#!/bin/bash

# script to check blockchain hashes in case they are foobar'd by 
# a newb that doesn't know how to extract blockchain wallet hashes
# by cyclone
# v2022.12.2-1930

# variables
output="cyclone_tmp_output"
hash="cyclone_tmp_hash"
input_clean="cyclone_input_clean"

# python2.7 version of blockchain2john.py is in included below and is xz compressed and base64 encoded
echo -n "/Td6WFoAAATm1rRGAgAhARYAAAB0L+Wj4ArCA6VdABGIQkeKIzPDdw8z/VWX7afH8OoqQzbHokaE
o0M6j4zKHmOtRMbC29mu1DlIhezKOF5Ggg/IKOf+ncIwE5S3uvBY3PrYmpzfS6+epehU5YVRx0RC
ku6V/aP54IJYB9mKyG9Pmap9fZpXJJIJbSayThjEKn/QA8/ctDcu2z5YTfMCIhmbVbTRIYSLYaFw
SY32W2OVOLSWWCoIzuZsznYf7a4xZQwdEbGvqUhnTNGFT3hQKvQ+q2v4zshGs5wSPDxtmXsKQHNJ
NzUeb+WFDymaMCoevVdwrPrrLykWgWSVb5njLuhJ4xjwGlSyj+/FtXOXPxLtPWGvgfI+2GMu4Fxo
+4GGaipPGMRthtfxsNiJuJA2Xfgh9DxXuZWQ8WhpULiSX9GMFK7mcS9/E6ZsKBLS/aAKqIPyBY7f
uADhw5e5m+LMJAOjNAruNfvyafqnaWMuL44gpAU96kccIr697jLL2n31uRMjw+8xbHhm2r+9tn70
1lKZJ7euKmCCsxvZafEl3XfGLhdvqekP36kPhHeQA+LA2OTYXwspEsK5HEAZuG3WmOHXY1qSc/Er
XKzZZDRjd+OfbCnbFXujkD27OuPxraNV5QmaEhF3FIQGMdSXu4M2U8k50h/FRIIsosQlUeLoEySz
1DmnE6iEoH07cTxpkzlw8HdCTuxSoNjiCZ9hbro5RSuck1KdFsoGO9Xv3OLNUYE8PRJwG+j4mC7o
PczgCJ+6f0nVf4mkPLwnCL1Rwawg3FC6gwePnAGt6UaPTLYERQOxQeVhcPCkes71/98sY1XPL70b
AFGHBMlut3D/0zDU4C6QjoWAdH2yU/BWnjNPrjGnC7rpaE9ujMX9FtdUyD6FONMrS/oEhKpb40yH
3pQXC4aHPBm2qr+CHawiKsHTkaDgCYf4XMn/pwlvPTONNkw+2g1bbp+6P1FzvPbHZ1P6fn+GpBVa
L01MrvvRLpBOceiFR58RK0d9pqNG+yrlrt12kdzhbExxRH3W2wtFo3p0doBKJ+zTTG1EKsfanHPG
F787Z+mUEAiLmSvjNj6kIHpU6vW+63vp3v8y7veTheEDVGpxTs+mHbiVrIrxXVAQ3aq33RqsX+te
AVgmxjBGuoLw04MGa5O9gVFBQVgK0ufFTu3Ojlnuyg3qt8/9Odf/HqhZtywINAdDRbFr+Z5k7j/f
icGQPdXFRT1ZDf9kCakfKYSUUbarzUj1LEA5RLHHQDJhwND/P8XBQwK7bVe9n0wLNwezdAAAAAAB
OqkFVqe6qQABwQfDFQAAr+XU1bHEZ/sCAAAAAARZWg==" | base64 -d | xz -d > blockchain2john.py
jtr_blockchain="python2.7 blockchain2john.py --base64 $output"

# check prerequisites
# python2.7
if ! command -v python2.7 -V &> /dev/null
then
	clear
    echo "Cannot find python2.7. Please make sure it is installed."
    exit
fi

# start script

clear

echo "Paste a single blockchain hash to check:"
echo
read input_raw

# parse input to remove invalid characters such as \t, \n, etc...
echo $input_raw | tr -d '\n'| tr -d "\t" | tr -d " " | egrep -i 'blockchain' > $input_clean

# main loop
while true; do
	# parse input hash and convert from hex to ascii
	cat $input_clean | rev | cut -d$ -f1 | rev | xxd -p -r > $output
	# sub loop to check if hash needs converted or not
	while true; do
		clear
		echo "Checking if hash needs converted..."
		sleep 0.5
		# run sanity check on hash
		cat $output | egrep -i '[[:print:]]{40,}' > /dev/null && break
		echo
		echo "Hash does not need converted."
		echo
		exit 1
		break
	done
	echo
	echo "Hash needs converted!"
	sleep 0.5
	echo
	echo "Converting hash..."
	sleep 0.5
	echo
	# run jtr_blockchain to convert hash
	$jtr_blockchain | cut -d: -f2 > $hash
	# final sanity check
	cat $hash | egrep -i '[[:print:]]{40,}' > /dev/null && cat $hash || echo "Could not convert hash."
	echo
	break
done

# clean up tmp files
rm $output $hash $input_raw $input_clean blockchain2john.py &> /dev/null