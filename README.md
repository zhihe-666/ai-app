# Flask + React 项目

基于 Flask + Vite + React + TypeScript 的全栈项目模板。

## 技术栈

- **后端**: Python + Flask + Flask-CORS
- **前端**: React + TypeScript + Vite

## 项目结构

```
├── backend/           # Flask 后端
│   ├── app.py         # 应用入口，默认端口 5000
│   └── requirements.txt
├── frontend/          # React 前端
│   ├── src/
│   │   ├── App.tsx    # 应用根组件
│   │   └── main.tsx   # 入口文件
│   ├── index.html
│   ├── package.json
│   ├── tsconfig.json
│   └── vite.config.ts
└── README.md
```

## 快速开始

### 后端

```bash
cd backend
pip install -r requirements.txt
python app.py
```

后端服务默认启动在 `http://127.0.0.1:5000`。

### 前端

```bash
cd frontend
npm install
npm run dev
```

前端 dev server 会自动代理 API 请求到后端。
