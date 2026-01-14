const state = {
  agents: [],
  templates: {},
  events: [],
  knowledge: [],
  timetable: [],
  curriculum: [],
  semester: null,
  simTime: null,
  lastTimestamp: 0,
  wsConnected: false,
  view: "control",
  rosterTab: "roster",
  filters: {
    outbound: true,
    inbound: false,
    role: "all",
  },
  bubbleTimers: new Map(),
  actionTimers: new Map(),
  seatLayout: null,
};

const statusPill = document.getElementById("status-pill");
const statusTick = document.getElementById("status-tick");
const statusTime = document.getElementById("status-time");
const statusCount = document.getElementById("status-count");
const feedList = document.getElementById("feed-list");
const agentsList = document.getElementById("agents-list");
const threadsList = document.getElementById("threads-list");
const filterOutbound = document.getElementById("filter-outbound");
const filterInbound = document.getElementById("filter-inbound");
const filterRole = document.getElementById("filter-role");
const tabRoster = document.getElementById("tab-roster");
const tabThreads = document.getElementById("tab-threads");
const viewControl = document.getElementById("view-control");
const viewClassroom = document.getElementById("view-classroom");
const controlView = document.getElementById("control-view");
const classroomView = document.getElementById("classroom-view");
const classroomAvatars = document.getElementById("classroom-avatars");
const seatGrid = document.getElementById("seat-grid");
const newTemplate = document.getElementById("new-template");
const knowledgeList = document.getElementById("knowledge-list");
const timetableList = document.getElementById("timetable-list");
const curriculumList = document.getElementById("curriculum-list");
const examWeeks = document.getElementById("exam-weeks");
const examPill = document.getElementById("exam-pill");
const examCurrent = document.getElementById("exam-current");
const startModal = document.getElementById("start-modal");
const startContinue = document.getElementById("start-continue");
const startReset = document.getElementById("start-reset");
const startCancel = document.getElementById("start-cancel");

const btnStart = document.getElementById("btn-start");
const btnPause = document.getElementById("btn-pause");
const btnResume = document.getElementById("btn-resume");
const btnStop = document.getElementById("btn-stop");
const btnReload = document.getElementById("btn-reload");
const btnRefresh = document.getElementById("btn-refresh");
const btnLoadAgents = document.getElementById("btn-load-agents");
const btnAddAgent = document.getElementById("btn-add-agent");
const btnResetScene = document.getElementById("btn-reset-scene");
const btnRefreshKnowledge = document.getElementById("btn-refresh-knowledge");
const btnRefreshTimetable = document.getElementById("btn-refresh-timetable");
const btnRefreshCurriculum = document.getElementById("btn-refresh-curriculum");
const btnRefreshSemester = document.getElementById("btn-refresh-semester");

function splitComma(value) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter((item) => item.length);
}

function toDisplayList(items) {
  if (!Array.isArray(items)) {
    return "";
  }
  return items.join(", ");
}

function resolveName(agentId) {
  const agent = state.agents.find((entry) => entry.id === agentId);
  return agent ? agent.name : agentId;
}

function resolveRole(agentId) {
  const agent = state.agents.find((entry) => entry.id === agentId);
  return agent ? agent.role : "unknown";
}

function displayTopic(topic) {
  const mapping = {
    lecture: "讲课",
    office_hours: "答疑",
    announcement: "公告",
    question: "提问",
    answer: "回答",
    ack: "确认",
    thanks: "感谢",
    feedback: "反馈",
    student_comment: "评论",
    peer_comment: "交流",
    peer_reply: "回复",
    summary: "总结",
    quiz: "测验",
    quiz_answer: "作答",
    quiz_score: "评分",
    noise: "课堂噪声",
    discipline: "管理",
    cold_call: "点名",
    review: "回顾",
    note: "记录",
  };
  return mapping[topic] || topic;
}

const topicStatus = {
  lecture: "记录",
  office_hours: "提问",
  question: "思考",
  answer: "点头",
  ack: "收到",
  thanks: "感谢",
  feedback: "困惑",
  student_comment: "分享",
  peer_comment: "交流",
  peer_reply: "回应",
  summary: "复盘",
  quiz: "测验",
  quiz_answer: "作答",
  quiz_score: "评分",
  noise: "走神",
  discipline: "提醒",
  cold_call: "点名",
  review: "回顾",
};

const topicAction = {
  lecture: "讲课",
  office_hours: "答疑",
  question: "举手",
  answer: "解答",
  student_comment: "发言",
  peer_comment: "讨论",
  peer_reply: "回应",
  summary: "总结",
  quiz: "出题",
  quiz_answer: "回答",
  quiz_score: "评分",
  noise: "走神",
  discipline: "管理",
  cold_call: "提问",
  review: "复盘",
};

function defaultStatus(role) {
  return role === "teacher" ? "讲解" : "专注";
}

function setView(view) {
  state.view = view;
  if (view === "control") {
    controlView.classList.remove("hidden");
    classroomView.classList.add("hidden");
    viewControl.classList.add("primary");
    viewControl.classList.remove("ghost");
    viewClassroom.classList.remove("primary");
    viewClassroom.classList.add("ghost");
  } else {
    controlView.classList.add("hidden");
    classroomView.classList.remove("hidden");
    viewClassroom.classList.add("primary");
    viewClassroom.classList.remove("ghost");
    viewControl.classList.remove("primary");
    viewControl.classList.add("ghost");
    renderClassroom();
  }
}

function setRosterTab(tab) {
  state.rosterTab = tab;
  if (tab === "roster") {
    agentsList.classList.remove("hidden");
    threadsList.classList.add("hidden");
    tabRoster.classList.add("active");
    tabThreads.classList.remove("active");
  } else {
    agentsList.classList.add("hidden");
    threadsList.classList.remove("hidden");
    tabThreads.classList.add("active");
    tabRoster.classList.remove("active");
    renderThreads();
  }
}

async function fetchStatus() {
  const res = await fetch("/status");
  const data = await res.json();
  statusTick.textContent = `${data.current_tick}/${data.ticks_total || 0}`;
  statusCount.textContent = `${data.agent_count || 0}`;
  if (statusTime) {
    const simTime = data.sim_time;
    state.simTime = simTime || null;
    renderExam();
    statusTime.textContent = simTime
      ? `${simTime.weekday} ${simTime.clock_time} ${simTime.date || ""} ${simTime.week_type || ""}`.trim()
      : "--";
  }
  if (data.running) {
    statusPill.textContent = data.paused ? "已暂停" : "运行中";
  } else {
    statusPill.textContent = "空闲";
  }
}

async function fetchAgents() {
  const res = await fetch("/agents");
  const data = await res.json();
  state.agents = data;
  renderAgents();
  renderClassroom();
  renderKnowledge();
  renderTimetable();
  await fetchStatus();
}

async function fetchTemplates() {
  const res = await fetch("/persona-templates");
  const data = await res.json();
  state.templates = data || {};
  renderTemplateOptions();
  renderAgents();
}

function renderTemplateOptions() {
  if (!newTemplate) {
    return;
  }
  newTemplate.innerHTML = '<option value="">模板（可选）</option>';
  Object.keys(state.templates).forEach((name) => {
    const option = document.createElement("option");
    option.value = name;
    option.textContent = name;
    newTemplate.appendChild(option);
  });
}

function templateOptions(selected) {
  const names = Object.keys(state.templates);
  const options = ['<option value="">模板</option>'];
  names.forEach((name) => {
    const mark = selected === name ? "selected" : "";
    options.push(`<option value="${name}" ${mark}>${name}</option>`);
  });
  return options.join("");
}

function renderAgents() {
  agentsList.innerHTML = "";
  state.agents.forEach((agent) => {
    const card = document.createElement("div");
    card.className = "agent-card";
    const persona = agent.persona || {};
    card.innerHTML = `
      <div class="agent-header">
        <span class="agent-title">${agent.name} (${agent.id})</span>
        <button class="btn ghost" data-action="delete">删除</button>
      </div>
      <div class="form-row">
        <input data-field="name" value="${agent.name}" />
        <input data-field="group" value="${agent.group}" />
      </div>
      <div class="form-row">
        <select data-field="role">
          <option value="student" ${agent.role === "student" ? "selected" : ""}>学生</option>
          <option value="teacher" ${agent.role === "teacher" ? "selected" : ""}>老师</option>
        </select>
        <input data-field="traits" value="${toDisplayList(persona.traits || [])}" placeholder="性格标签" />
        <input data-field="interests" value="${toDisplayList(persona.interests || [])}" placeholder="兴趣" />
      </div>
      <div class="form-row">
        <input data-field="tone" value="${persona.tone || ""}" placeholder="语气" />
        <input data-field="bio" value="${persona.bio || ""}" placeholder="简介" />
      </div>
      <div class="form-row">
        <select data-field="template">${templateOptions("")}</select>
        <button class="btn ghost" data-action="apply-template">应用模板</button>
      </div>
      <div class="button-row">
        <button class="btn primary" data-action="save">保存</button>
      </div>
    `;
    card.querySelector('[data-action="save"]').onclick = () => saveAgent(agent.id, card);
    card.querySelector('[data-action="delete"]').onclick = () => deleteAgent(agent.id);
    card.querySelector('[data-action="apply-template"]').onclick = () =>
      applyTemplate(agent.id, card);
    agentsList.appendChild(card);
  });
}

function renderFeed() {
  feedList.innerHTML = "";
  const filtered = state.events.filter((event) => {
    if (event.direction === "outbound" && !state.filters.outbound) {
      return false;
    }
    if (event.direction === "inbound" && !state.filters.inbound) {
      return false;
    }
    if (state.filters.role !== "all") {
      const role = resolveRole(event.sender_id);
      if (role !== state.filters.role) {
        return false;
      }
    }
    return true;
  });
  filtered
    .slice()
    .reverse()
    .forEach((event) => {
      const sender = resolveName(event.sender_id);
      const receiver = event.receiver_id ? resolveName(event.receiver_id) : "all";
      const time = new Date(event.timestamp * 1000).toLocaleTimeString();
      const topicLabel = displayTopic(event.topic);
      const item = document.createElement("div");
      item.className = "feed-item";
      item.innerHTML = `
        <div class="feed-meta">
          <span>${time} · ${topicLabel}</span>
          <span>${sender} -> ${receiver}</span>
        </div>
        <div>${event.content}</div>
      `;
      feedList.appendChild(item);
    });
}

function renderThreads() {
  threadsList.innerHTML = "";
  const outboundEvents = state.events.filter((event) => event.direction === "outbound");
  const grouped = {};
  outboundEvents.forEach((event) => {
    if (!grouped[event.sender_id]) {
      grouped[event.sender_id] = [];
    }
    grouped[event.sender_id].push(event);
  });
  const renderGroup = (role) => {
    const header = document.createElement("div");
    header.className = "thread-title";
    header.textContent = role === "teacher" ? "老师" : "学生";
    threadsList.appendChild(header);
    state.agents
      .filter((agent) => agent.role === role)
      .forEach((agent) => {
        const events = (grouped[agent.id] || []).slice(-4).reverse();
        const card = document.createElement("div");
        card.className = "thread-card";
        card.innerHTML = `
          <div class="thread-title">${agent.name}</div>
          <div>${events.map((item) => `- ${item.content}`).join("<br />") || "暂无消息。"}</div>
        `;
        threadsList.appendChild(card);
      });
  };
  renderGroup("teacher");
  renderGroup("student");
}

function renderKnowledge() {
  if (!knowledgeList) {
    return;
  }
  knowledgeList.innerHTML = "";
  if (!state.agents.length) {
    const empty = document.createElement("div");
    empty.className = "hint";
    empty.textContent = "暂无角色数据。";
    knowledgeList.appendChild(empty);
    return;
  }
  const grouped = new Map();
  state.knowledge.forEach((item) => {
    if (!item || !item.agent_id) {
      return;
    }
    if (!grouped.has(item.agent_id)) {
      grouped.set(item.agent_id, []);
    }
    grouped.get(item.agent_id).push(item);
  });
  const students = state.agents.filter((agent) => agent.role === "student");
  if (!students.length) {
    const empty = document.createElement("div");
    empty.className = "hint";
    empty.textContent = "暂无学生角色。";
    knowledgeList.appendChild(empty);
    return;
  }
  students.forEach((agent) => {
    const card = document.createElement("div");
    card.className = "knowledge-card";
    const title = document.createElement("div");
    title.className = "knowledge-title";
    const nameSpan = document.createElement("span");
    nameSpan.textContent = agent.name;
    const groupSpan = document.createElement("span");
    groupSpan.textContent = agent.group || "";
    title.appendChild(nameSpan);
    title.appendChild(groupSpan);
    card.appendChild(title);

    const items = grouped.get(agent.id) || [];
    items.sort((a, b) => (b.updated_at || 0) - (a.updated_at || 0));
    const limited = items.slice(0, 6);
    if (!limited.length) {
      const empty = document.createElement("div");
      empty.className = "hint";
      empty.textContent = "暂无理解度记录。";
      card.appendChild(empty);
    } else {
      limited.forEach((item) => {
        const percent = Math.max(0, Math.min(100, Math.round((item.score || 0) * 100)));
        const row = document.createElement("div");
        row.className = "knowledge-row";
        const topicSpan = document.createElement("span");
        topicSpan.textContent = item.topic || "主题";
        const percentSpan = document.createElement("span");
        percentSpan.textContent = `${percent}%`;
        row.appendChild(topicSpan);
        row.appendChild(percentSpan);
        const bar = document.createElement("div");
        bar.className = "knowledge-bar";
        const fill = document.createElement("div");
        fill.className = "knowledge-fill";
        fill.style.width = `${percent}%`;
        bar.appendChild(fill);
        card.appendChild(row);
        card.appendChild(bar);
      });
    }
    knowledgeList.appendChild(card);
  });
}

function renderTimetable() {
  if (!timetableList) {
    return;
  }
  timetableList.innerHTML = "";
  if (!state.timetable.length) {
    const empty = document.createElement("div");
    empty.className = "hint";
    empty.textContent = "暂无课表数据。";
    timetableList.appendChild(empty);
    return;
  }
  const grouped = {};
  state.timetable.forEach((entry) => {
    const group = entry.group || "all";
    if (!grouped[group]) {
      grouped[group] = [];
    }
    grouped[group].push(entry);
  });
  Object.keys(grouped)
    .sort()
    .forEach((group) => {
      const card = document.createElement("div");
      card.className = "timetable-card";
      const title = document.createElement("div");
      title.className = "timetable-title";
      title.textContent = group;
      card.appendChild(title);
      grouped[group]
        .slice()
        .sort((a, b) => (a.start_time || "").localeCompare(b.start_time || ""))
        .forEach((entry) => {
          const weekdays = Array.isArray(entry.weekdays)
            ? entry.weekdays.join(",")
            : entry.weekdays || "";
          const teacherName = entry.teacher_id
            ? resolveName(entry.teacher_id)
            : "未知";
          const line = document.createElement("div");
          line.textContent = `${weekdays} ${entry.start_time} ${entry.topic} · ${teacherName}`;
          card.appendChild(line);
        });
      timetableList.appendChild(card);
    });
}

function renderCurriculum() {
  if (!curriculumList) {
    return;
  }
  curriculumList.innerHTML = "";
  if (!state.curriculum.length) {
    const empty = document.createElement("div");
    empty.className = "hint";
    empty.textContent = "暂无课程数据。";
    curriculumList.appendChild(empty);
    return;
  }
  state.curriculum.forEach((course) => {
    const card = document.createElement("div");
    card.className = "curriculum-card";
    const title = document.createElement("div");
    title.className = "curriculum-title";
    const nameSpan = document.createElement("span");
    nameSpan.textContent = course.name || course.course_id || "课程";
    const progress =
      course.progress === null || course.progress === undefined
        ? null
        : Math.max(0, Math.min(100, Math.round(course.progress * 100)));
    const progressSpan = document.createElement("span");
    progressSpan.textContent = progress === null ? "--" : `${progress}%`;
    title.appendChild(nameSpan);
    title.appendChild(progressSpan);
    card.appendChild(title);

    const bar = document.createElement("div");
    bar.className = "curriculum-bar";
    const fill = document.createElement("div");
    fill.className = "curriculum-fill";
    fill.style.width = progress === null ? "0%" : `${progress}%`;
    bar.appendChild(fill);
    card.appendChild(bar);

    (course.concepts || []).forEach((item) => {
      const row = document.createElement("div");
      row.className = "curriculum-row";
      const label = document.createElement("span");
      label.textContent = item.name || item.id || "知识点";
      const score =
        item.score === null || item.score === undefined
          ? null
          : Math.max(0, Math.min(100, Math.round(item.score * 100)));
      const value = document.createElement("span");
      value.textContent = score === null ? "--" : `${score}%`;
      row.appendChild(label);
      row.appendChild(value);
      const cbar = document.createElement("div");
      cbar.className = "curriculum-bar";
      const cfill = document.createElement("div");
      cfill.className = "curriculum-fill";
      cfill.style.width = score === null ? "0%" : `${score}%`;
      cbar.appendChild(cfill);
      card.appendChild(row);
      card.appendChild(cbar);
    });

    curriculumList.appendChild(card);
  });
}

async function fetchCurriculumProgress() {
  const res = await fetch("/curriculum-progress");
  const data = await res.json();
  state.curriculum = Array.isArray(data.courses) ? data.courses : [];
  renderCurriculum();
}

function renderExam() {
  if (!examWeeks || !examPill || !examCurrent) {
    return;
  }
  const simTime = state.simTime || {};
  const weekType = simTime.week_type || "--";
  const weekMode = simTime.week_mode || "";
  examCurrent.textContent = weekType === "--" ? "--" : `当前：${weekType}`;
  if (weekMode === "exam") {
    examPill.textContent = "考试周";
    examPill.classList.add("exam");
  } else if (weekMode === "review") {
    examPill.textContent = "复习周";
    examPill.classList.remove("exam");
  } else {
    examPill.textContent = "教学周";
    examPill.classList.remove("exam");
  }
  examWeeks.innerHTML = "";
  const weeks =
    state.semester && Array.isArray(state.semester.exam_weeks)
      ? state.semester.exam_weeks
      : [];
  if (!weeks.length) {
    const empty = document.createElement("div");
    empty.className = "hint";
    empty.textContent = "暂无考试周配置。";
    examWeeks.appendChild(empty);
    return;
  }
  weeks.forEach((week) => {
    const chip = document.createElement("div");
    chip.className = "exam-week";
    chip.textContent = `第${week}周`;
    examWeeks.appendChild(chip);
  });
}

async function fetchSemester() {
  const res = await fetch("/semester");
  const data = await res.json();
  state.semester = data || {};
  renderExam();
}

function showStartModal() {
  if (!startModal) {
    return;
  }
  startModal.classList.remove("hidden");
}

function hideStartModal() {
  if (!startModal) {
    return;
  }
  startModal.classList.add("hidden");
}

async function startSimulation(mode) {
  await fetch("/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode }),
  });
  hideStartModal();
  await fetchStatus();
}

async function fetchTimetable() {
  const res = await fetch("/timetable");
  const data = await res.json();
  state.timetable = Array.isArray(data) ? data : [];
  renderTimetable();
}

async function fetchKnowledge() {
  const res = await fetch("/knowledge");
  const data = await res.json();
  state.knowledge = Array.isArray(data) ? data : [];
  renderKnowledge();
}

async function saveAgent(agentId, card) {
  const name = card.querySelector('[data-field="name"]').value.trim();
  const group = card.querySelector('[data-field="group"]').value.trim();
  const role = card.querySelector('[data-field="role"]').value;
  const traits = splitComma(card.querySelector('[data-field="traits"]').value);
  const interests = splitComma(card.querySelector('[data-field="interests"]').value);
  const tone = card.querySelector('[data-field="tone"]').value.trim();
  const bio = card.querySelector('[data-field="bio"]').value.trim();
  await fetch(`/agents/${agentId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name,
      group,
      role,
      persona: { traits, interests, tone, bio },
    }),
  });
  await fetchAgents();
  renderThreads();
}

async function applyTemplate(agentId, card) {
  const template = card.querySelector('[data-field="template"]').value;
  if (!template) {
    return;
  }
  await fetch(`/agents/${agentId}/apply-template`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ template }),
  });
  await fetchAgents();
}

async function deleteAgent(agentId) {
  await fetch(`/agents/${agentId}`, { method: "DELETE" });
  await fetchAgents();
}

async function addAgent() {
  const id = document.getElementById("new-id").value.trim();
  const name = document.getElementById("new-name").value.trim();
  const role = document.getElementById("new-role").value;
  const group = document.getElementById("new-group").value.trim();
  const template = newTemplate ? newTemplate.value : "";
  const traits = splitComma(document.getElementById("new-traits").value);
  const interests = splitComma(document.getElementById("new-interests").value);
  const tone = document.getElementById("new-tone").value.trim();
  const bio = document.getElementById("new-bio").value.trim();
  if (!id || !name || !group) {
    return;
  }
  let persona = { traits, interests, tone, bio };
  if (template && state.templates[template]) {
    persona = state.templates[template];
  }
  await fetch("/agents", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      id,
      name,
      role,
      group,
      llm: { enabled: true },
      persona,
    }),
  });
  document.getElementById("new-id").value = "";
  document.getElementById("new-name").value = "";
  document.getElementById("new-group").value = "";
  document.getElementById("new-traits").value = "";
  document.getElementById("new-interests").value = "";
  document.getElementById("new-tone").value = "";
  document.getElementById("new-bio").value = "";
  if (newTemplate) {
    newTemplate.value = "";
  }
  await fetchAgents();
}

function ingestEvent(event) {
  if (!event || !event.timestamp) {
    return;
  }
  if (event.timestamp > state.lastTimestamp) {
    state.lastTimestamp = event.timestamp;
  }
  state.events.push(event);
  if (state.events.length > 240) {
    state.events.shift();
  }
  renderFeed();
  renderThreads();
  if (event.direction === "outbound") {
    updateBubble(event.sender_id, event.content, event.topic);
  }
}

async function fetchMessages() {
  if (state.wsConnected) {
    return;
  }
  const url =
    state.lastTimestamp > 0
      ? `/messages?limit=80&since=${state.lastTimestamp}`
      : "/messages?limit=80";
  const res = await fetch(url);
  const data = await res.json();
  if (!Array.isArray(data) || data.length === 0) {
    return;
  }
  data
    .slice()
    .reverse()
    .forEach((event) => ingestEvent(event));
}

function connectWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${protocol}://${window.location.host}/ws`);
  ws.onopen = () => {
    state.wsConnected = true;
  };
  ws.onclose = () => {
    state.wsConnected = false;
    setTimeout(connectWebSocket, 2000);
  };
  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      ingestEvent(data);
    } catch {
      // ignore
    }
  };
}

function buildSeatLayout(count) {
  const columns = Math.min(5, Math.max(3, Math.ceil(Math.sqrt(count || 1))));
  const rows = Math.max(1, Math.ceil((count || 1) / columns));
  const area = { left: 12, top: 210, width: 76, height: 260 };
  const colGap = columns > 1 ? area.width / (columns - 1) : 0;
  const rowGap = rows > 1 ? area.height / (rows - 1) : 0;
  const seats = [];
  for (let row = 0; row < rows; row += 1) {
    for (let col = 0; col < columns; col += 1) {
      seats.push({
        left: area.left + col * colGap,
        top: area.top + row * rowGap,
      });
    }
  }
  return { seats, columns, rows, area };
}

function renderSeatGrid(layout) {
  if (!seatGrid) {
    return;
  }
  seatGrid.innerHTML = "";
  layout.seats.forEach((seat) => {
    const seatEl = document.createElement("div");
    seatEl.className = "seat";
    seatEl.style.left = `${seat.left}%`;
    seatEl.style.top = `${seat.top}px`;
    seatGrid.appendChild(seatEl);
  });
}

function renderClassroom() {
  classroomAvatars.innerHTML = "";
  if (seatGrid) {
    seatGrid.innerHTML = "";
  }
  if (!state.agents.length) {
    return;
  }
  const teachers = state.agents.filter((agent) => agent.role === "teacher");
  const students = state.agents.filter((agent) => agent.role === "student");
  const layout = buildSeatLayout(students.length);
  state.seatLayout = layout;
  renderSeatGrid(layout);
  const teacherSpread = 12;
  const teacherStart = 50 - ((teachers.length - 1) * teacherSpread) / 2;
  teachers.forEach((agent, index) => {
    const left = teacherStart + index * teacherSpread;
    const avatar = createAvatar(agent, left, 140, {
      walkRange: { min: left - 8, max: left + 8 },
    });
    classroomAvatars.appendChild(avatar);
  });
  students.forEach((agent, index) => {
    const seat = layout.seats[index];
    if (!seat) {
      return;
    }
    const avatar = createAvatar(agent, seat.left, seat.top - 14);
    classroomAvatars.appendChild(avatar);
  });
}

function createAvatar(agent, leftPercent, topPx, options = {}) {
  const avatar = document.createElement("div");
  avatar.className = `avatar ${agent.role}`;
  avatar.dataset.agentId = agent.id;
  avatar.dataset.role = agent.role;
  avatar.dataset.baseLeft = `${leftPercent}`;
  avatar.dataset.baseTop = `${topPx}`;
  avatar.dataset.defaultStatus = defaultStatus(agent.role);
  if (options.walkRange) {
    avatar.dataset.walkMin = `${options.walkRange.min}`;
    avatar.dataset.walkMax = `${options.walkRange.max}`;
    avatar.dataset.walkDir = "1";
  }
  avatar.style.left = `${leftPercent}%`;
  avatar.style.top = `${topPx}px`;
  avatar.style.setProperty("--dx", `${(Math.random() * 2 - 1) * 4}px`);
  avatar.style.setProperty("--dy", `${(Math.random() * 2 - 1) * 4}px`);
  const nameEl = document.createElement("span");
  nameEl.className = "avatar-name";
  nameEl.textContent = agent.name.slice(0, 2);
  const statusEl = document.createElement("span");
  statusEl.className = "avatar-status";
  statusEl.textContent = avatar.dataset.defaultStatus;
  const actionEl = document.createElement("span");
  actionEl.className = "avatar-action";
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  avatar.appendChild(nameEl);
  avatar.appendChild(statusEl);
  avatar.appendChild(actionEl);
  avatar.appendChild(bubble);
  return avatar;
}

function applyAvatarExpression(avatar, topic) {
  const statusEl = avatar.querySelector(".avatar-status");
  const actionEl = avatar.querySelector(".avatar-action");
  if (!statusEl || !actionEl) {
    return;
  }
  const defaultText = avatar.dataset.defaultStatus || "专注";
  const status = topicStatus[topic] || defaultText;
  const action = topicAction[topic] || "";
  statusEl.textContent = status;
  if (action) {
    actionEl.textContent = action;
    avatar.classList.add("action");
  } else {
    actionEl.textContent = "";
    avatar.classList.remove("action");
  }
  const timerId = state.actionTimers.get(avatar.dataset.agentId);
  if (timerId) {
    clearTimeout(timerId);
  }
  const newTimer = setTimeout(() => {
    statusEl.textContent = defaultText;
    avatar.classList.remove("action");
  }, 3600);
  state.actionTimers.set(avatar.dataset.agentId, newTimer);
}

function updateBubble(agentId, content, topic) {
  const avatar = classroomAvatars.querySelector(
    `.avatar[data-agent-id="${agentId}"]`
  );
  if (!avatar) {
    return;
  }
  const bubble = avatar.querySelector(".bubble");
  if (!bubble) {
    return;
  }
  bubble.textContent = content.slice(0, 120);
  bubble.classList.add("active");
  avatar.classList.add("speaking");
  applyAvatarExpression(avatar, topic);
  const timerId = state.bubbleTimers.get(agentId);
  if (timerId) {
    clearTimeout(timerId);
  }
  const newTimer = setTimeout(() => {
    bubble.classList.remove("active");
    avatar.classList.remove("speaking");
  }, 4000);
  state.bubbleTimers.set(agentId, newTimer);
}

function animateClassroom() {
  if (state.view !== "classroom") {
    return;
  }
  const avatars = classroomAvatars.querySelectorAll(".avatar");
  avatars.forEach((avatar) => {
    const role = avatar.dataset.role;
    if (role === "teacher") {
      const min = parseFloat(avatar.dataset.walkMin || avatar.dataset.baseLeft);
      const max = parseFloat(avatar.dataset.walkMax || avatar.dataset.baseLeft);
      let current = parseFloat(avatar.style.left);
      if (Number.isNaN(current)) {
        current = parseFloat(avatar.dataset.baseLeft || "50");
      }
      let direction = parseFloat(avatar.dataset.walkDir || "1");
      let next = current + direction * (2 + Math.random() * 2);
      if (next > max || next < min) {
        direction *= -1;
        next = Math.max(min, Math.min(max, next));
      }
      avatar.dataset.walkDir = `${direction}`;
      avatar.style.left = `${next}%`;
      avatar.style.setProperty("--dx", `${(Math.random() * 2 - 1) * 4}px`);
      avatar.style.setProperty("--dy", `${(Math.random() * 2 - 1) * 2}px`);
    } else {
      const dx = (Math.random() * 2 - 1) * 5;
      const dy = (Math.random() * 2 - 1) * 3;
      avatar.style.setProperty("--dx", `${dx}px`);
      avatar.style.setProperty("--dy", `${dy}px`);
    }
  });
}

btnStart.onclick = async () => {
  showStartModal();
};

btnPause.onclick = async () => {
  await fetch("/pause", { method: "POST" });
  await fetchStatus();
};

btnResume.onclick = async () => {
  await fetch("/resume", { method: "POST" });
  await fetchStatus();
};

btnStop.onclick = async () => {
  await fetch("/stop", { method: "POST" });
  await fetchStatus();
};

btnReload.onclick = async () => {
  await fetch("/reload", { method: "POST" });
  state.lastTimestamp = 0;
  state.events = [];
  feedList.innerHTML = "";
  await fetchStatus();
};

if (startContinue) {
  startContinue.onclick = async () => {
    await startSimulation("continue");
  };
}

if (startReset) {
  startReset.onclick = async () => {
    await startSimulation("reset");
  };
}

if (startCancel) {
  startCancel.onclick = () => {
    hideStartModal();
  };
}

btnRefresh.onclick = async () => {
  state.lastTimestamp = 0;
  state.events = [];
  feedList.innerHTML = "";
  await fetchMessages();
};

btnLoadAgents.onclick = async () => {
  await fetchAgents();
};

btnAddAgent.onclick = async () => {
  await addAgent();
};

btnResetScene.onclick = () => {
  renderClassroom();
};

if (btnRefreshKnowledge) {
  btnRefreshKnowledge.onclick = async () => {
    await fetchKnowledge();
  };
}

if (btnRefreshTimetable) {
  btnRefreshTimetable.onclick = async () => {
    await fetchTimetable();
  };
}


if (btnRefreshCurriculum) {
  btnRefreshCurriculum.onclick = async () => {
    await fetchCurriculumProgress();
  };
}

if (btnRefreshSemester) {
  btnRefreshSemester.onclick = async () => {
    await fetchSemester();
  };
}
filterOutbound.onchange = () => {
  state.filters.outbound = filterOutbound.checked;
  renderFeed();
};

filterInbound.onchange = () => {
  state.filters.inbound = filterInbound.checked;
  renderFeed();
};

filterRole.onchange = () => {
  state.filters.role = filterRole.value;
  renderFeed();
};

tabRoster.onclick = () => setRosterTab("roster");
tabThreads.onclick = () => setRosterTab("threads");
viewControl.onclick = () => setView("control");
viewClassroom.onclick = () => setView("classroom");

async function bootstrap() {
  await fetchTemplates();
  await fetchAgents();
  await fetchMessages();
  await fetchKnowledge();
  await fetchTimetable();
  await fetchCurriculumProgress();
  await fetchSemester();
  connectWebSocket();
  setInterval(fetchStatus, 1500);
  setInterval(fetchMessages, 1500);
  setInterval(fetchKnowledge, 3000);
  setInterval(fetchCurriculumProgress, 6000);
  setInterval(fetchSemester, 12000);
  setInterval(animateClassroom, 1200);
  setView("control");
  setRosterTab("roster");
}

bootstrap();









