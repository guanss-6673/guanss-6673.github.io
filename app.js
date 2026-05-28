const state = {
  currentStep: 1,
  stepCount: 1,
  generated: null,
};

const stepCards = Array.from(document.querySelectorAll('.step'));
const stepperItems = Array.from(document.querySelectorAll('#stepper li'));
const stepOrder = stepperItems
  .map((el) => Number(el.dataset.step))
  .filter((n) => Number.isFinite(n))
  .sort((a, b) => a - b);
state.stepCount = Math.max(
  stepCards.length,
  stepperItems.length,
  ...stepCards.map((el) => Number(el.dataset.step) || 0),
  ...stepperItems.map((el) => Number(el.dataset.step) || 0)
);
if (!stepOrder.includes(state.currentStep) && stepOrder.length > 0) {
  state.currentStep = stepOrder[0];
}

const prevBtn = document.getElementById('prevBtn');
const nextBtn = document.getElementById('nextBtn');
const messageEl = document.getElementById('message');
const generateBtn = document.getElementById('generateBtn');
const submitBtn = document.getElementById('submitBtn');
const exportBtn = document.getElementById('exportBtn');
const fileInputIds = [
  'orderFiles',
  'operationFiles',
  'centerFiles',
  'staffFiles',
  'calendarShiftFiles',
  'constraintFiles',
];

function init() {
  bindEvents();
  refreshStepUI();
}

function bindEvents() {
  prevBtn.addEventListener('click', () => moveStep(-1));
  nextBtn.addEventListener('click', () => moveStep(1));
  stepperItems.forEach((item) => {
    item.addEventListener('click', () => goStep(Number(item.dataset.step)));
  });

  generateBtn.addEventListener('click', () => {
    state.generated = buildPayload();
    renderResult(state.generated);
    setMessage('已生成结构化需求摘要。');
  });

  submitBtn.addEventListener('click', async () => {
    const payload = state.generated || buildPayload();
    if (!state.generated) {
      state.generated = payload;
      renderResult(payload);
    }
    submitBtn.disabled = true;
    setMessage('正在提交到服务器...');
    try {
      const formData = new FormData();
      formData.append('payload', JSON.stringify(payload));
      for (const inputId of fileInputIds) {
        const inputEl = document.getElementById(inputId);
        if (!inputEl || !inputEl.files) continue;
        Array.from(inputEl.files).forEach((file) => {
          formData.append(`files__${inputId}`, file, file.name);
        });
      }

      const resp = await fetch('/api/submissions', {
        method: 'POST',
        body: formData,
      });
      if (!resp.ok) {
        const text = await resp.text();
        throw new Error(text || `HTTP ${resp.status}`);
      }
      const result = await resp.json();
      setMessage(`提交成功，编号：${result.submission_id}，文件数：${result.saved_file_count}`);
    } catch (err) {
      setMessage(`提交失败：${err.message}`);
    } finally {
      submitBtn.disabled = false;
    }
  });

  exportBtn.addEventListener('click', () => {
    const payload = state.generated || buildPayload();
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `scheduling_requirement_${timestamp()}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
    setMessage('已导出 JSON。');
  });
}

function moveStep(delta) {
  const idx = stepOrder.indexOf(state.currentStep);
  if (idx < 0) return;
  const nextIdx = clamp(idx + delta, 0, stepOrder.length - 1);
  state.currentStep = stepOrder[nextIdx];
  refreshStepUI();
}

function goStep(step) {
  state.currentStep = clamp(step, 1, state.stepCount);
  refreshStepUI();
}

function refreshStepUI() {
  stepCards.forEach((card) => card.classList.remove('active'));
  stepperItems.forEach((item) => item.classList.remove('active'));

  const activeCard = document.querySelector(`.step[data-step="${state.currentStep}"]`);
  if (activeCard) activeCard.classList.add('active');
  const activeStepItem = stepperItems.find((item) => Number(item.dataset.step) === state.currentStep);
  if (activeStepItem) activeStepItem.classList.add('active');

  prevBtn.disabled = stepOrder.indexOf(state.currentStep) === 0;
  nextBtn.style.display = stepOrder.indexOf(state.currentStep) === stepOrder.length - 1 ? 'none' : 'inline-block';
  setMessage('');
}

function buildPayload() {
  return {
    scenario: '生产排程',
    objective_default: '所有订单按期交付',
    generated_at: new Date().toISOString(),
    section_task_and_goal: {
      task_overview: value('taskOverview'),
      task_goal: value('taskGoal'),
    },
    section_order_input: {
      summary: value('orderSummary'),
      uploaded_files: fileNames('orderFiles'),
    },
    section_operation_input: {
      summary: value('operationSummary'),
      uploaded_files: fileNames('operationFiles'),
    },
    section_work_center_input: {
      summary: value('centerSummary'),
      uploaded_files: fileNames('centerFiles'),
    },
    section_staff_input: {
      summary: value('staffSummary'),
      uploaded_files: fileNames('staffFiles'),
    },
    section_calendar_shift_input: {
      standard_shift_window: value('standardShiftWindow'),
      daily_working_hours: value('dailyWorkingHours'),
      weekly_work_pattern: value('weeklyWorkPattern'),
      fixed_break_window: value('fixedBreakWindow'),
      overtime_policy: value('overtimePolicy'),
      summary: value('calendarShiftSummary'),
      uploaded_files: fileNames('calendarShiftFiles'),
    },
    section_constraints: {
      constraints_overview: value('constraintsOverview'),
      special_constraints: value('specialConstraints'),
      uploaded_files: fileNames('constraintFiles'),
    },
    section_expected_output: {
      output_description: value('expectedOutput'),
      output_tables: [
        '生产计划表',
        '工序明细表',
        '物料齐套与采购表',
        '产线负荷表',
        '人员排班表',
      ],
    },
  };
}

function renderResult(payload) {
  const panel = document.getElementById('resultPanel');
  const jsonPreview = document.getElementById('jsonPreview');
  panel.classList.remove('hidden');
  jsonPreview.textContent = JSON.stringify(payload, null, 2);
}

function value(id) {
  const el = document.getElementById(id);
  return el ? el.value.trim() : '';
}

function fileNames(id) {
  const el = document.getElementById(id);
  if (!el || !el.files) return [];
  return Array.from(el.files).map((f) => f.name);
}

function timestamp() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}_${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`;
}

function setMessage(text) {
  messageEl.textContent = text;
}

function clamp(n, min, max) {
  return Math.max(min, Math.min(max, n));
}

init();
