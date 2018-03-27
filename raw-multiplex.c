#include <unistd.h>
#include <stdio.h>
#include <stdint.h>
#include <fcntl.h>
#include <stdlib.h>

int main(int argc, char **argv) {
    if (argc < 7) {
        fprintf(stderr, "usage: %s <stream 1 raw> <stream 2 raw> <width> <height> <numframes> <BYTES_PER_PIXEL>\n", argv[0]);
        return 1;
    }
    int s1 = open(argv[1], O_RDONLY);
    int s2 = open(argv[2], O_RDONLY);
    if (s1 < 0 || s2 < 0) {
        fprintf(stderr, "failed to open streams!");
        return 1;
    }
    
    int width = atoi(argv[3]), height = atoi(argv[4]), numframes = atoi(argv[5]), bpp = atoi(argv[6]);
    int halfrow = bpp * width;
    uint8_t buf[halfrow * 2];
    
    ssize_t r1 = 1, r2 = 1;
    size_t donedata = 0, totaldata = numframes * bpp * width * height * 2;
    int doneframes = 0, ignore = 0;
    
    // Continue until given number of frames have been processed (will hang on EOF?!)
    while (1 || r1 > 0 || r2 > 0) {
        r1 = read(s1, buf, halfrow);
        r2 = read(s2, buf + halfrow, halfrow);
        if (r1 < halfrow || r2 < halfrow) {
            fprintf(stderr, "\nread %ld from s1, %ld from s2, expected %d bytes\n", r1, r2, halfrow);
        }
        if (donedata < totaldata) {
            // Read extra frames but don't output them
            donedata += write(STDOUT_FILENO, buf, sizeof(buf));
        } else if (!ignore) {
            fprintf(stderr, "\nskipping remaining frames...\n");
            ignore = 1;
        } else if (r1 <= 0 && r2 <= 0 && donedata >= totaldata) {
            break;
        } 
    }
    
    close(s1);
    close(s2);
}
