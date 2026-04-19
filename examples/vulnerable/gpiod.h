#ifndef ECLIPSE_BENCHMARK_GPIOD_H
#define ECLIPSE_BENCHMARK_GPIOD_H

/*
 * Benchmark-only libgpiod shim.
 *
 * ECLIPSE's GPIO pass replaces supported read calls with symbolic values before
 * execution. This header only exists to make standalone preprocessing and
 * compilation succeed without a real libgpiod install.
 */

struct gpiod_chip;
struct gpiod_request_config;
struct gpiod_line_settings;
struct gpiod_line_config;
struct gpiod_line_request;

#define GPIOD_LINE_DIRECTION_INPUT 1

static inline struct gpiod_chip *
gpiod_chip_open(const char *path)
{
    (void) path;
    return (struct gpiod_chip *) 1;
}

static inline struct gpiod_request_config *
gpiod_request_config_new(void)
{
    return (struct gpiod_request_config *) 1;
}

static inline void
gpiod_request_config_set_consumer(struct gpiod_request_config *config, const char *consumer)
{
    (void) config;
    (void) consumer;
}

static inline struct gpiod_line_settings *
gpiod_line_settings_new(void)
{
    return (struct gpiod_line_settings *) 1;
}

static inline int
gpiod_line_settings_set_direction(struct gpiod_line_settings *settings, int direction)
{
    (void) settings;
    (void) direction;
    return 0;
}

static inline struct gpiod_line_config *
gpiod_line_config_new(void)
{
    return (struct gpiod_line_config *) 1;
}

static inline int
gpiod_line_config_add_line_settings(
    struct gpiod_line_config *config,
    const unsigned int *offsets,
    unsigned long num_offsets,
    struct gpiod_line_settings *settings
)
{
    (void) config;
    (void) offsets;
    (void) num_offsets;
    (void) settings;
    return 0;
}

static inline struct gpiod_line_request *
gpiod_chip_request_lines(
    struct gpiod_chip *chip,
    struct gpiod_request_config *request_config,
    struct gpiod_line_config *line_config
)
{
    (void) chip;
    (void) request_config;
    (void) line_config;
    return (struct gpiod_line_request *) 1;
}

/*
 * Fallback only: the intended benchmark path is that ECLIPSE rewrites this
 * call to a symbolic GPIO value before execution.
 */
static inline int
gpiod_line_request_get_value(struct gpiod_line_request *request, unsigned int offset)
{
    (void) request;
    (void) offset;
    return 0;
}

static inline void
gpiod_line_request_release(struct gpiod_line_request *request)
{
    (void) request;
}

static inline void
gpiod_line_config_free(struct gpiod_line_config *config)
{
    (void) config;
}

static inline void
gpiod_line_settings_free(struct gpiod_line_settings *settings)
{
    (void) settings;
}

static inline void
gpiod_request_config_free(struct gpiod_request_config *config)
{
    (void) config;
}

static inline void
gpiod_chip_close(struct gpiod_chip *chip)
{
    (void) chip;
}

#endif
