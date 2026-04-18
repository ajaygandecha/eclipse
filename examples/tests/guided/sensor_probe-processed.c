extern int snprintf(char *str, unsigned long size, const char *format, ...);
extern void klee_make_symbolic(void *addr, unsigned long nbytes, const char *name);
extern void klee_assume(int condition);
extern void klee_assert(int condition);

static char *__eclipse_int_to_string(int value, char *buffer, int buffer_size)
{
  snprintf(buffer, buffer_size, "%d", value);
  return buffer;
}

int same_flag(char *left, char *right)
{
  int i = 0;
  int __eclipse_loop_bound_0 = 0;
  while (((left[i] != '\0') && (right[i] != '\0')) && (__eclipse_loop_bound_0 < 10))
  {
    if (left[i] != right[i])
    {
      return 0;
    }
    i++;
    __eclipse_loop_bound_0++;
  }

  return left[i] == right[i];
}

int parse_int(char *value)
{
  int result = 0;
  int i = 0;
  int __eclipse_loop_bound_1 = 0;
  while ((value[i] != '\0') && (__eclipse_loop_bound_1 < 10))
  {
    result = (result * 10) + (value[i] - '0');
    i++;
    __eclipse_loop_bound_1++;
  }

  return result;
}

int string_length(char *value)
{
  int length = 0;
  int __eclipse_loop_bound_2 = 0;
  while ((value[length] != '\0') && (__eclipse_loop_bound_2 < 10))
  {
    length++;
    __eclipse_loop_bound_2++;
  }

  return length;
}

int rolling_checksum(char *payload, int retry_budget)
{
  int i = 0;
  int checksum = 0;
  int __eclipse_loop_bound_3 = 0;
  while ((payload[i] != '\0') && (__eclipse_loop_bound_3 < 10))
  {
    checksum += payload[i] * ((i + 1) + retry_budget);
    i++;
    __eclipse_loop_bound_3++;
  }

  return checksum;
}

int parse_transport_header(char *payload, int sample_count)
{
  int payload_length = string_length(payload);
  int score = 0;
  int i = 0;
  int __eclipse_loop_bound_4 = 0;
  while ((i < (sample_count + 3)) && (__eclipse_loop_bound_4 < 10))
  {
    int current = payload[i % payload_length];
    if ((current & 1) == 0)
    {
      score += current;
    }
    else
    {
      score -= current;
    }
    if (current == 'A')
    {
      score += 7;
    }
    else
      if (current == 'B')
    {
      score += 5;
    }
    else
      if (current == 'C')
    {
      score -= 3;
    }
    else
    {
      score += i;
    }
    i++;
    __eclipse_loop_bound_4++;
  }

  return score;
}

int service_watchdog(char *payload, int sample_count)
{
  int payload_length = string_length(payload);
  int budget = 0;
  int i = 0;
  int __eclipse_loop_bound_5 = 0;
  while ((i < (sample_count + 4)) && (__eclipse_loop_bound_5 < 10))
  {
    int current = payload[(i + 1) % payload_length];
    if (current < 'M')
    {
      budget += 2;
    }
    else
    {
      budget -= 1;
    }
    if ((current == 'X') || (current == 'Y'))
    {
      budget += 4;
    }
    i++;
    __eclipse_loop_bound_5++;
  }

  return budget;
}

int collect_telemetry(char *payload, int sample_count)
{
  int payload_length = string_length(payload);
  int digest = 1;
  int i = 0;
  int __eclipse_loop_bound_6 = 0;
  while ((i < (sample_count + 3)) && (__eclipse_loop_bound_6 < 10))
  {
    int current = payload[i % payload_length];
    if (current == 'Q')
    {
      digest *= 2;
    }
    else
      if (current == 'R')
    {
      digest += 9;
    }
    else
      if ((current % 3) == 0)
    {
      digest += current;
    }
    else
    {
      digest -= i;
    }
    i++;
    __eclipse_loop_bound_6++;
  }

  return digest;
}

int build_diagnostic_frame(char *payload, int sample_count, int diag_mode)
{
  char frame[4];
  int payload_length = string_length(payload);
  int i = 0;
  int checksum = 0;
  int bytes_to_copy;
  if (payload_length == 0)
  {
    return 0;
  }
  int __eclipse_loop_bound_7 = 0;
  while ((i < 4) && (__eclipse_loop_bound_7 < 10))
  {
    frame[i] = 0;
    i++;
    __eclipse_loop_bound_7++;
  }

  if (diag_mode)
  {
    bytes_to_copy = (sample_count + payload_length) + 1;
    i = 0;
    int __eclipse_loop_bound_8 = 0;
    while ((i < bytes_to_copy) && (__eclipse_loop_bound_8 < 10))
    {
      frame[i] = payload[i % payload_length];
      i++;
      __eclipse_loop_bound_8++;
    }

  }
  else
  {
    bytes_to_copy = sample_count;
    if (bytes_to_copy > 3)
    {
      bytes_to_copy = 3;
    }
    i = 0;
    int __eclipse_loop_bound_9 = 0;
    while ((i < bytes_to_copy) && (__eclipse_loop_bound_9 < 10))
    {
      frame[i] = payload[i % payload_length];
      i++;
      __eclipse_loop_bound_9++;
    }

  }
  i = 0;
  int __eclipse_loop_bound_10 = 0;
  while ((i < 4) && (__eclipse_loop_bound_10 < 10))
  {
    checksum += frame[i];
    i++;
    __eclipse_loop_bound_10++;
  }

  return checksum;
}

int dispatch_probe(char *payload, int sample_count, int diag_mode)
{
  int payload_length = string_length(payload);
  if (!diag_mode)
  {
    return parse_transport_header(payload, sample_count);
  }
  if (payload_length < 2)
  {
    return service_watchdog(payload, sample_count);
  }
  if (payload[0] == 'Q')
  {
    return build_diagnostic_frame(payload, sample_count, diag_mode);
  }
  if (payload[0] < 'Q')
  {
    return collect_telemetry(payload, sample_count);
  }
  return service_watchdog(payload, sample_count);
}

int __eclipse_original_main(int argc, char **argv)
{
  int index = 1;
  int diag_mode = 0;
  int sample_count = 1;
  char *payload = "ok";
  int __eclipse_loop_bound_11 = 0;
  while ((index < argc) && (__eclipse_loop_bound_11 < 10))
  {
    if (same_flag(argv[index], "-D") || same_flag(argv[index], "--diag"))
    {
      diag_mode = 1;
      index++;
    }
    else
      if (same_flag(argv[index], "-s") || same_flag(argv[index], "--samples"))
    {
      if ((index + 1) >= argc)
      {
        return 2;
      }
      sample_count = parse_int(argv[index + 1]);
      index += 2;
    }
    else
    {
      payload = argv[index];
      break;
    }
    __eclipse_loop_bound_11++;
  }

  return dispatch_probe(payload, sample_count, diag_mode) + rolling_checksum(payload, sample_count);
}

int main(void)
{
  int __eclipse_argc = 1;
  char *__eclipse_argv[6];
  __eclipse_argv[0] = "sensor-probe";
  int __eclipse_use_diag_mode;
  klee_make_symbolic(&__eclipse_use_diag_mode, sizeof(__eclipse_use_diag_mode), "diag_mode_present");
  klee_assume((__eclipse_use_diag_mode == 0) || (__eclipse_use_diag_mode == 1));
  int __eclipse_diag_mode_spelling;
  klee_make_symbolic(&__eclipse_diag_mode_spelling, sizeof(__eclipse_diag_mode_spelling), "diag_mode_spelling");
  klee_assume((__eclipse_diag_mode_spelling >= 0) && (__eclipse_diag_mode_spelling <= 1));
  int __eclipse_use_sample_flag;
  klee_make_symbolic(&__eclipse_use_sample_flag, sizeof(__eclipse_use_sample_flag), "sample_flag_present");
  klee_assume((__eclipse_use_sample_flag == 0) || (__eclipse_use_sample_flag == 1));
  int __eclipse_sample_flag_spelling;
  klee_make_symbolic(&__eclipse_sample_flag_spelling, sizeof(__eclipse_sample_flag_spelling), "sample_flag_spelling");
  klee_assume((__eclipse_sample_flag_spelling >= 0) && (__eclipse_sample_flag_spelling <= 1));
  int sym_sample_count;
  klee_make_symbolic(&sym_sample_count, sizeof(sym_sample_count), "sample_count");
  klee_assume((sym_sample_count >= 0) && (sym_sample_count <= 2));
  char __eclipse_sample_count_value[2];
  int __eclipse_use_payload;
  klee_make_symbolic(&__eclipse_use_payload, sizeof(__eclipse_use_payload), "payload_present");
  klee_assume((__eclipse_use_payload == 0) || (__eclipse_use_payload == 1));
  int __eclipse_payload_length;
  klee_make_symbolic(&__eclipse_payload_length, sizeof(__eclipse_payload_length), "payload_length");
  klee_assume((__eclipse_payload_length >= 1) && (__eclipse_payload_length <= 2));
  char sym_payload[3];
  klee_make_symbolic(sym_payload, sizeof(sym_payload), "payload");
  klee_assume(sym_payload[__eclipse_payload_length] == '\0');
  klee_assume((__eclipse_payload_length <= 0) || (sym_payload[0] != '\0'));
  klee_assume((__eclipse_payload_length <= 1) || (sym_payload[1] != '\0'));
  if (__eclipse_use_diag_mode)
  {
    if (__eclipse_diag_mode_spelling == 0)
    {
      __eclipse_argv[__eclipse_argc] = "-D";
      __eclipse_argc++;
    }
    if (__eclipse_diag_mode_spelling == 1)
    {
      __eclipse_argv[__eclipse_argc] = "--diag";
      __eclipse_argc++;
    }
  }
  if (__eclipse_use_sample_flag)
  {
    if (__eclipse_sample_flag_spelling == 0)
    {
      __eclipse_argv[__eclipse_argc] = "-s";
      __eclipse_argc++;
    }
    if (__eclipse_sample_flag_spelling == 1)
    {
      __eclipse_argv[__eclipse_argc] = "--samples";
      __eclipse_argc++;
    }
  }
  if (__eclipse_use_sample_flag)
  {
    __eclipse_argv[__eclipse_argc] = __eclipse_int_to_string(sym_sample_count, __eclipse_sample_count_value, sizeof(__eclipse_sample_count_value));
    __eclipse_argc++;
  }
  if (__eclipse_use_payload)
  {
    __eclipse_argv[__eclipse_argc] = sym_payload;
    __eclipse_argc++;
  }
  __eclipse_argv[__eclipse_argc] = 0;
  return __eclipse_original_main(__eclipse_argc, __eclipse_argv);
}

