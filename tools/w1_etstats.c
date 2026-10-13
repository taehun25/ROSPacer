/* Read-only Linux ethtool statistics. No driver/firmware settings changed. */
#include <errno.h>
#include <inttypes.h>
#include <linux/ethtool.h>
#include <linux/sockios.h>
#include <net/if.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <unistd.h>

static void json_string(const unsigned char *s, size_t n) {
    putchar('"');
    for (size_t i=0;i<n && s[i];i++) {
        if (s[i]=='"' || s[i]=='\\') putchar('\\');
        if (s[i]<32) printf("\\u%04x",s[i]); else putchar(s[i]);
    }
    putchar('"');
}

int main(int argc,char **argv) {
    if (argc!=2 || strlen(argv[1])>=IFNAMSIZ) return 2;
    struct ifreq req={0};strncpy(req.ifr_name,argv[1],IFNAMSIZ-1);
    int fd=socket(AF_INET,SOCK_DGRAM,0);
    if (fd<0) {perror("socket");return 1;}
    struct ethtool_drvinfo info={.cmd=ETHTOOL_GDRVINFO};req.ifr_data=(void *)&info;
    if (ioctl(fd,SIOCETHTOOL,&req)<0) {perror("GDRVINFO");close(fd);return 1;}
    unsigned n=info.n_stats;
    if (!n || n>4096) {fprintf(stderr,"invalid statistics count %u\n",n);close(fd);return 1;}
    struct ethtool_gstrings *names=calloc(1,sizeof(*names)+(size_t)n*ETH_GSTRING_LEN);
    struct ethtool_stats *stats=calloc(1,sizeof(*stats)+(size_t)n*sizeof(uint64_t));
    if (!names || !stats) {free(names);free(stats);close(fd);return 1;}
    names->cmd=ETHTOOL_GSTRINGS;names->string_set=ETH_SS_STATS;names->len=n;req.ifr_data=(void *)names;
    if (ioctl(fd,SIOCETHTOOL,&req)<0) {perror("GSTRINGS");free(names);free(stats);close(fd);return 1;}
    stats->cmd=ETHTOOL_GSTATS;stats->n_stats=n;req.ifr_data=(void *)stats;
    if (ioctl(fd,SIOCETHTOOL,&req)<0) {perror("GSTATS");free(names);free(stats);close(fd);return 1;}
    printf("{\"stats\":{");
    for (unsigned i=0;i<n;i++) {
        if (i) putchar(',');json_string(names->data+(size_t)i*ETH_GSTRING_LEN,ETH_GSTRING_LEN);
        printf(":%" PRIu64,(uint64_t)stats->data[i]);
    }
    printf("},\"count\":%u}\n",n);free(names);free(stats);close(fd);return 0;
}
