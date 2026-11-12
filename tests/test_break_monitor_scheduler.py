# -*- coding: utf-8 -*-
"""v3.4.2 断点监控调度器 TDD (S1-S9).

对应实施文档 docs/EXECUTION_V3.4.2_BREAK_SCHEDULER.md §4。
Red 预期: backtest.structural_break_monitor 无 BreakMonitorScheduler → 收集错误。

调度语义:
- daily / weekly / monthly 三档节拍, 以周期键 (日/ISO 周/月) 判定到期;
- 同一周期重复调用幂等 (只运行一次); 周期键变化即到期 (支持历史回放);
- 回调抛异常时不推进状态, 同周期可重试。
"""
import unittest
from pathlib import Path
import sys

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backtest.structural_break_monitor import (
    BreakMonitorConfig,
    BreakMonitorScheduler,
    StructuralBreakMonitor,
)


class TestCadence(unittest.TestCase):
    """S1-S3: 三档节拍的周期键判定."""

    def test_s1_daily_same_date_idempotent(self):
        sched = BreakMonitorScheduler(cadence='daily')
        self.assertTrue(sched.due('2026-11-10 09:00'))
        sched.mark_run('2026-11-10 09:00')
        self.assertFalse(sched.due('2026-11-10 15:00'),
                         "同一天不同时刻不应重复运行")
        self.assertTrue(sched.due('2026-11-11 09:00'))

    def test_s2_weekly_uses_iso_week_across_year_boundary(self):
        sched = BreakMonitorScheduler(cadence='weekly')
        sched.mark_run('2025-12-28')          # 2025-W52 周日
        self.assertFalse(sched.due('2025-12-28'))
        self.assertTrue(sched.due('2025-12-29'),   # 2026-W01 周一 (ISO 年切换)
                        "ISO 周应按 ISO 年+周判定, 而非日历年")
        sched.mark_run('2025-12-29')
        self.assertFalse(sched.due('2026-01-04'),  # 仍在 2026-W01
                         "跨公历年但同一 ISO 周不应重复运行")
        self.assertTrue(sched.due('2026-01-05'))   # 2026-W02

    def test_s3_monthly_same_month_idempotent(self):
        sched = BreakMonitorScheduler(cadence='monthly')
        sched.mark_run('2026-01-31')
        self.assertFalse(sched.due('2026-01-01'),
                         "同月回退日期仍属同一周期键")
        self.assertTrue(sched.due('2026-02-01'))

    def test_s4_invalid_cadence_raises(self):
        with self.assertRaises(ValueError) as ctx:
            BreakMonitorScheduler(cadence='quarterly')
        self.assertIn('daily', str(ctx.exception))
        self.assertIn('weekly', str(ctx.exception))
        self.assertIn('monthly', str(ctx.exception))

    def test_s10_weekly_same_week_no_different_iso_year(self):
        """ISO 年分量必须是键的一部分 (2025-W01 vs 2026-W01)."""
        sched = BreakMonitorScheduler(cadence='weekly')
        sched.mark_run('2024-12-30')          # 2025-W01 周一
        self.assertTrue(sched.due('2025-12-29'),
                        "周号相同但 ISO 年不同, 必须到期")

    def test_s11_daily_monthly_key_includes_year(self):
        daily = BreakMonitorScheduler(cadence='daily')
        daily.mark_run('2025-12-31')
        self.assertTrue(daily.due('2026-12-31'),
                        "同月日但跨年, daily 必须到期")

        monthly = BreakMonitorScheduler(cadence='monthly')
        monthly.mark_run('2025-12-15')
        self.assertTrue(monthly.due('2026-12-15'),
                        "同月但跨年, monthly 必须到期")

    def test_s16_iso_53_week_year(self):
        """2026 为 ISO 53 周年; 2027-01-03 仍属 2026-W53."""
        sched = BreakMonitorScheduler(cadence='weekly')
        sched.mark_run('2026-12-28')          # 2026-W53
        self.assertFalse(sched.due('2027-01-03'),
                         "2027-01-03 仍属 2026-W53, 不应重复运行")
        self.assertTrue(sched.due('2027-01-04'))   # 2027-W01


class TestValidation(unittest.TestCase):
    """S5: as_of 非法输入显式失败."""

    def test_s5_invalid_as_of_raises(self):
        sched = BreakMonitorScheduler(cadence='monthly')
        for bad in (None, pd.NaT, 'not-a-date', object()):
            with self.subTest(as_of=repr(bad)):
                with self.assertRaises(ValueError):
                    sched.due(bad)

    def test_s5_date_and_datetime_accepted(self):
        from datetime import date, datetime
        sched = BreakMonitorScheduler(cadence='daily')
        self.assertTrue(sched.due(date(2026, 11, 10)))
        sched.mark_run(datetime(2026, 11, 10, 18, 30))
        self.assertFalse(sched.due('2026-11-10'))

    def test_s13_numeric_as_of_rejected(self):
        """数值型会被 pandas 解释为 1970 纳秒时间戳, 必须显式拒绝."""
        sched = BreakMonitorScheduler(cadence='daily')
        for bad in (20260105, 20260105.0, np.int64(20260105),
                    np.float64(20260105.0)):
            with self.subTest(as_of=repr(bad)):
                with self.assertRaises(ValueError) as ctx:
                    sched.due(bad)
                self.assertIn('数值', str(ctx.exception))
        # numpy datetime64 仍可用
        self.assertTrue(sched.due(np.datetime64('2026-01-05')))
        with self.assertRaises(ValueError):
            sched.due(np.datetime64('NaT'))

    def test_s14_tz_aware_as_of_rejected(self):
        sched = BreakMonitorScheduler(cadence='daily')
        for bad in (pd.Timestamp('2026-01-05', tz='Asia/Shanghai'),
                    '2026-01-05T00:00:00+08:00'):
            with self.subTest(as_of=repr(bad)):
                with self.assertRaises(ValueError) as ctx:
                    sched.due(bad)
                self.assertIn('naive', str(ctx.exception))

    def test_s15_cadence_is_read_only(self):
        sched = BreakMonitorScheduler(cadence='monthly')
        with self.assertRaises(AttributeError):
            sched.cadence = 'weekly'


class TestRunIfDue(unittest.TestCase):
    """S6-S9: 回调执行、异常不推进、重置、与真实监控器集成."""

    def test_s6_run_if_due_executes_once_per_period(self):
        sched = BreakMonitorScheduler(cadence='monthly')
        calls = []

        def _job(tag):
            calls.append(tag)
            return {'detected': False, 'tag': tag}

        r1 = sched.run_if_due('2026-01-05', _job, 1)
        r2 = sched.run_if_due('2026-01-20', _job, 2)
        r3 = sched.run_if_due('2026-02-01', _job, 3)

        self.assertEqual(r1, {'detected': False, 'tag': 1})
        self.assertIsNone(r2, "同月跳过应返回 None")
        self.assertEqual(r3, {'detected': False, 'tag': 3})
        self.assertEqual(calls, [1, 3], "回调只应在到期周期执行")
        self.assertEqual(sched.runs, 2)
        self.assertEqual(sched.last_run_as_of, pd.Timestamp('2026-02-01'))

    def test_s7_failure_does_not_advance_state(self):
        sched = BreakMonitorScheduler(cadence='monthly')

        def _boom():
            raise RuntimeError('boom')

        with self.assertRaises(RuntimeError):
            sched.run_if_due('2026-01-05', _boom)
        self.assertEqual(sched.runs, 0)
        self.assertIsNone(sched.last_run_as_of)
        self.assertTrue(sched.due('2026-01-06'),
                        "失败后同周期仍应到期, 允许重试")

    def test_s8_reset_rearms_first_call(self):
        sched = BreakMonitorScheduler(cadence='monthly')
        self.assertEqual(sched.run_if_due('2026-01-05', lambda: 1), 1)
        sched.reset()
        self.assertTrue(sched.due('2026-01-06'))
        self.assertEqual(sched.runs, 0)
        self.assertIsNone(sched.last_run_as_of)

    def test_s12_callback_returning_none_still_advances(self):
        """回调返回 None 不等于未到期: 状态必须推进."""
        sched = BreakMonitorScheduler(cadence='monthly')

        r = sched.run_if_due('2026-01-05', lambda: None)
        self.assertIsNone(r)
        self.assertEqual(sched.runs, 1,
                         "回调返回 None 也必须计为一次运行")
        self.assertFalse(sched.due('2026-01-20'))

    def test_s17_failure_then_retry_really_runs(self):
        sched = BreakMonitorScheduler(cadence='monthly')
        attempts = []

        def _job():
            attempts.append(1)
            if len(attempts) == 1:
                raise RuntimeError('first attempt fails')
            return {'ok': True}

        with self.assertRaises(RuntimeError):
            sched.run_if_due('2026-01-05', _job)
        self.assertTrue(sched.due('2026-01-06'), "失败后同周期应可重试")
        r = sched.run_if_due('2026-01-06', _job)
        self.assertEqual(r, {'ok': True})
        self.assertEqual(sched.runs, 1)
        self.assertEqual(sched.last_run_as_of, pd.Timestamp('2026-01-06'))
        self.assertFalse(sched.due('2026-01-20'))

    def test_s9_integration_with_structural_break_monitor(self):
        sched = BreakMonitorScheduler(cadence='monthly')
        mon = StructuralBreakMonitor(BreakMonitorConfig(
            method='sup_f', n_bootstrap=50, min_points=20, random_state=42))
        path = pd.Series(
            np.r_[np.zeros(30), np.ones(30)],
            index=pd.date_range('2020-01-01', periods=60, freq='D'))

        r1 = sched.run_if_due('2026-01-05', mon.detect, path)
        r2 = sched.run_if_due('2026-01-25', mon.detect, path)
        r3 = sched.run_if_due('2026-02-05', mon.detect, path)

        self.assertIsInstance(r1, dict)
        self.assertEqual(r1['n_points'], 60)
        self.assertIsNone(r2)
        self.assertIsInstance(r3, dict)
        self.assertEqual(sched.runs, 2)


class TestBoundaries(unittest.TestCase):
    """S18-S21: 闰日、run_if_due 入口校验、历史回放、mark_run 计数."""

    def test_s18_leap_day(self):
        daily = BreakMonitorScheduler(cadence='daily')
        daily.mark_run('2028-02-29')
        self.assertFalse(daily.due('2028-02-29 23:00'))
        self.assertTrue(daily.due('2028-03-01'))

        monthly = BreakMonitorScheduler(cadence='monthly')
        monthly.mark_run('2028-02-15')
        self.assertTrue(monthly.due('2028-03-01'))

    def test_s19_invalid_as_of_does_not_invoke_callback(self):
        sched = BreakMonitorScheduler(cadence='monthly')
        calls = []

        def _job():
            calls.append(1)

        with self.assertRaises(ValueError):
            sched.run_if_due('not-a-date', _job)
        self.assertEqual(calls, [], "校验失败必须在回调之前")
        self.assertEqual(sched.runs, 0)

    def test_s20_backward_period_triggers_rerun(self):
        """周期键变化即到期: 历史回放会再次执行 (文档已明示)."""
        sched = BreakMonitorScheduler(cadence='monthly')
        sched.mark_run('2026-02-15')
        self.assertTrue(sched.due('2026-01-15'))
        self.assertEqual(sched.run_if_due('2026-01-15', lambda: 'replay'),
                         'replay')
        self.assertEqual(sched.runs, 2)

    def test_s21_mark_run_counts_each_call(self):
        sched = BreakMonitorScheduler(cadence='monthly')
        sched.mark_run('2026-01-05')
        sched.mark_run('2026-01-20')
        self.assertEqual(sched.runs, 2, "手工登记按调用次数计数")
        self.assertEqual(sched.last_run_as_of, pd.Timestamp('2026-01-20'))


if __name__ == '__main__':
    unittest.main()
