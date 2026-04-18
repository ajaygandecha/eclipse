#ifndef _FAKE_SYS_SYSMACROS_H
#define _FAKE_SYS_SYSMACROS_H

#define major(dev) (((dev) >> 8) & 0xff)
#define minor(dev) ((dev) & 0xff)
#define makedev(maj, min) (((maj) << 8) | (min))

#endif
