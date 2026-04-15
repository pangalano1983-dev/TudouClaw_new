# 前端开发模版 (Frontend Development Template)

**tags:** frontend, ui-development, component-design, performance
**roles:** Frontend Developer, UI Developer, Frontend Architect
**category:** Development

## 目标 (Objective)

指导前端开发的最佳实践，确保可维护、高性能和用户友好的应用程序。

## 组件设计 (Component Design)

### 组件架构 (Component Architecture)

```
组件分类:

1. 基础组件 (Base Components)
   ├── Button
   ├── Input
   ├── Label
   ├── Card
   └── Modal

2. 容器组件 (Container Components)
   ├── Header
   ├── Navigation
   ├── Sidebar
   ├── Footer
   └── Layout

3. 业务组件 (Business Components)
   ├── UserProfile
   ├── ProductCard
   ├── OrderForm
   └── DashboardWidget

4. 页面组件 (Page Components)
   ├── HomePage
   ├── ProductPage
   ├── CheckoutPage
   └── UserSettingsPage
```

### 组件设计规范 (Component Specification)

```
组件名: [ButtonComponent]
类别: 基础组件
用途: [描述]
依赖: [列出依赖]

属性 (Props):
{
  "label": {
    "type": "string",
    "required": true,
    "description": "按钮文本",
    "default": ""
  },
  "variant": {
    "type": "enum",
    "values": ["primary", "secondary", "danger"],
    "default": "primary"
  },
  "size": {
    "type": "enum",
    "values": ["sm", "md", "lg"],
    "default": "md"
  },
  "disabled": {
    "type": "boolean",
    "default": false
  },
  "onClick": {
    "type": "function",
    "description": "点击处理函数"
  }
}

事件 (Events):
[ ] onClick - 用户点击
[ ] onFocus - 获得焦点
[ ] onBlur - 失去焦点

插槽 (Slots):
[ ] default - 按钮内容
[ ] icon - 按钮图标

可访问性 (Accessibility):
[ ] ARIA 标签
[ ] 键盘导航 (Tab, Enter)
[ ] 屏幕阅读器支持
[ ] 颜色对比度检查 (WCAG AA)

测试:
[ ] 单元测试: 95% 覆盖率
[ ] 快照测试: 已完成
[ ] 可视化回归测试: 已完成
```

### 组件 API 设计 (Component API)

```javascript
// React 示例

// 合理的 API（清晰、灵活）
<Button
  variant="primary"
  size="lg"
  onClick={handleClick}
  disabled={isLoading}
>
  Submit
</Button>

// 糟糕的 API（不清晰、不灵活）
<Button
  type="submit_large_enabled"
  onClickFunction={handleClick}
/>

// 最佳实践:
[ ] 单一职责原则
[ ] Props 命名一致
[ ] 合理的默认值
[ ] 支持扩展（render props, slots）
[ ] 逆向兼容性
```

## 状态管理 (State Management)

### 状态管理策略 (State Management Strategy)

```
选择标准:

简单应用 (< 5 页) → 本地状态 + Context API
中等应用 (5-20 页) → Redux / Zustand
复杂应用 (> 20 页) → Redux + 中间件

推荐栈:
[ ] 小型应用: React Hooks + Context
[ ] 中等应用: Zustand / Jotai
[ ] 大型应用: Redux Toolkit
```

### 全局状态结构 (Global State Structure)

```javascript
// Redux 状态树示例

{
  // 用户模块
  user: {
    profile: { id, name, email },
    preferences: { theme, language },
    loading: false,
    error: null
  },

  // 产品模块
  products: {
    items: [{ id, name, price }],
    filters: { category, priceRange },
    pagination: { page, total },
    loading: false,
    error: null
  },

  // UI 模块
  ui: {
    modals: { loginOpen, settingsOpen },
    notifications: [{ id, type, message }],
    sidebarOpen: true
  },

  // 购物车模块
  cart: {
    items: [{ productId, quantity }],
    total: 0,
    lastUpdated: timestamp
  }
}

// 状态设计原则:
[ ] 规范化数据 (避免嵌套)
[ ] 分离关注点 (多个 reducer)
[ ] 包含加载和错误状态
[ ] 时间旅行调试支持
```

### 本地 vs 全局状态 (Local vs Global State)

```
本地状态 (Local State):
- 表单输入值
- 模态打开/关闭
- 内联编辑状态
- 加载指示器（仅组件）

全局状态 (Global State):
- 当前登录用户
- 用户偏好设置
- 数据列表
- 认证令牌
- 应用配置

规则:
[ ] 优先使用本地状态
[ ] 仅当需要跨组件共享时提升为全局
[ ] 不要在全局状态中存储 UI 状态
```

## 性能优化 (Performance Optimization)

### 代码拆分 (Code Splitting)

```javascript
// 路由级别代码拆分
import { lazy, Suspense } from 'react';

const HomePage = lazy(() => import('./pages/Home'));
const ProductPage = lazy(() => import('./pages/Product'));

<Suspense fallback={<Loading />}>
  <Routes>
    <Route path="/" element={<HomePage />} />
    <Route path="/product/:id" element={<ProductPage />} />
  </Routes>
</Suspense>

// 结果:
[ ] 初始包大小: 150 KB
[ ] Home 页面包: 50 KB
[ ] Product 页面包: 60 KB
[ ] 共享依赖: 40 KB

性能提升: 首次加载时间减少 60%
```

### 渲染优化 (Rendering Optimization)

```javascript
// 1. React.memo - 防止不必要的重新渲染
const ProductCard = React.memo(({ product, onSelect }) => {
  return <div onClick={onSelect}>{product.name}</div>;
}, (prevProps, nextProps) => {
  return prevProps.product.id === nextProps.product.id;
});

// 2. useMemo - 缓存计算结果
const expensiveValue = useMemo(() => {
  return complexCalculation(data);
}, [data]);

// 3. useCallback - 缓存函数引用
const handleClick = useCallback(() => {
  doSomething(value);
}, [value]);

// 4. 虚拟化长列表
import { FixedSizeList as List } from 'react-window';

<List
  height={600}
  itemCount={10000}
  itemSize={35}
  width="100%"
>
  {({ index, style }) => (
    <div style={style}>{items[index]}</div>
  )}
</List>

性能指标:
[ ] 首次内容绘制 (FCP): < 1.8s
[ ] 最大内容绘制 (LCP): < 2.5s
[ ] 首次输入延迟 (FID): < 100ms
```

### 资源优化 (Resource Optimization)

```
图片优化:
[ ] 使用现代格式 (WebP)
[ ] 提供响应式图片 (srcset)
[ ] 实现懒加载
[ ] 压缩和优化尺寸
[ ] 使用 CDN

示例:
<picture>
  <source srcSet="image.webp" type="image/webp" />
  <source srcSet="image.jpg" type="image/jpeg" />
  <img src="image.jpg" alt="" loading="lazy" />
</picture>

CSS 优化:
[ ] 关键 CSS 内联
[ ] 分离非关键 CSS
[ ] 移除未使用的 CSS
[ ] 最小化和压缩
[ ] 使用 CSS-in-JS 条件加载

JavaScript 优化:
[ ] Tree-shaking 移除死代码
[ ] 最小化和压缩
[ ] 延迟加载非关键脚本
[ ] 使用异步/延迟加载属性
[ ] 预加载关键脚本
```

## 可访问性 (Accessibility)

### WCAG 2.1 合规性 (WCAG 2.1 Compliance)

```
A 级（最低）- 必须满足:
[ ] 1.4.3 色彩对比度 (4.5:1 for text)
[ ] 2.1.1 键盘可访问
[ ] 2.5.5 目标大小 (44x44px)
[ ] 4.1.2 名称、角色、值（表单）

AA 级（推荐）- 应该满足:
[ ] 1.4.3 增强对比度 (7:1)
[ ] 2.4.3 焦点顺序合理
[ ] 3.3.1 错误识别和建议
[ ] 3.3.4 错误预防

AAA 级（高级）- 可以满足:
[ ] 1.4.3 最高对比度 (3:1)
[ ] 2.5.5 大目标大小 (60x60px)
```

### 可访问性实施 (Accessibility Implementation)

```html
<!-- 合理的 HTML -->
<button aria-label="关闭" onClick={onClose}>
  <CloseIcon />
</button>

<label htmlFor="email">Email</label>
<input
  id="email"
  type="email"
  aria-required="true"
  aria-invalid={hasError}
  aria-describedby="email-error"
/>
<span id="email-error" role="alert">
  {error}
</span>

<!-- 键盘导航 -->
<dialog>
  <button autoFocus>主要行动</button>
  <button>次要行动</button>
</dialog>

实施清单:
[ ] 语义 HTML (<button> vs <div>)
[ ] ARIA 标签和描述
[ ] 键盘导航支持
[ ] 焦点管理
[ ] 屏幕阅读器测试
[ ] 颜色对比度检查
[ ] 焦点指示器可见
```

## 响应式设计 (Responsive Design)

### 断点策略 (Breakpoint Strategy)

```css
/* 移动优先方法 */

/* 基础 - 手机 (320px+) */
.container {
  padding: 16px;
  font-size: 14px;
}

/* 平板 (768px+) */
@media (min-width: 768px) {
  .container {
    padding: 24px;
    font-size: 16px;
  }
}

/* 桌面 (1024px+) */
@media (min-width: 1024px) {
  .container {
    padding: 32px;
    font-size: 18px;
    max-width: 1200px;
  }
}

/* 大屏幕 (1440px+) */
@media (min-width: 1440px) {
  .container {
    max-width: 1400px;
  }
}

推荐断点:
[ ] 手机: 320px, 480px
[ ] 平板: 768px, 1024px
[ ] 桌面: 1280px, 1920px
```

### 灵活布局 (Flexible Layout)

```css
/* Flexbox 布局 */
.flex-container {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
}

.flex-item {
  flex: 1 1 250px;
  min-width: 250px;
}

/* Grid 布局 */
.grid-container {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 24px;
}

/* 容器查询（现代） */
@container (min-width: 400px) {
  .card {
    display: grid;
    grid-template-columns: 100px 1fr;
  }
}

最佳实践:
[ ] 流式布局（没有固定宽度）
[ ] 灵活排版（rem 相对单位）
[ ] 触摸友好（最小 44px 目标）
[ ] 优化大屏幕（max-width 限制）
```

## 浏览器兼容性 (Browser Compatibility)

### 支持矩阵 (Support Matrix)

```
浏览器          版本      支持    注意
───────────────────────────────────────
Chrome          最后 2 版  完全   默认
Firefox         最后 2 版  完全
Safari          最后 2 版  完全   iOS 12+
Edge            最后 2 版  完全
IE 11           最后     部分    降级体验

Polyfills 需求:
[ ] Babel 编译现代 JS
[ ] 浏览器 API polyfills
[ ] CSS 前缀 (autoprefixer)
[ ] Promise polyfill (IE 11)
[ ] Fetch polyfill (IE 11)
```

### 功能检测和降级 (Feature Detection & Graceful Degradation)

```javascript
// 检测功能支持
if ('IntersectionObserver' in window) {
  // 使用 IntersectionObserver
} else {
  // 降级方案：使用滚动事件
}

// CSS 功能支持
@supports (display: grid) {
  .grid {
    display: grid;
  }
}

@supports not (display: grid) {
  .grid {
    display: flex;
    flex-wrap: wrap;
  }
}

// 渐进增强
[ ] 基础功能在所有浏览器工作
[ ] 增强功能在现代浏览器中
[ ] 优雅降级无功能损失
```

## 前端测试 (Frontend Testing)

### 测试金字塔 (Test Pyramid)

```
          /\
         /  \       E2E 测试 (10%)
        /    \      用户流程
       /──────\
      /        \    集成测试 (20%)
     /          \   组件交互
    /────────────\
   /              \  单元测试 (70%)
   ─────────────────  函数和组件
     Unit Tests

目标:
[ ] 单元测试: >= 80% 覆盖率
[ ] 集成测试: 关键流程
[ ] E2E 测试: 用户旅程
```

### 单元测试示例 (Unit Test Example)

```javascript
import { render, screen, fireEvent } from '@testing-library/react';
import Button from './Button';

describe('Button Component', () => {
  it('should render with text', () => {
    render(<Button>Click me</Button>);
    expect(screen.getByRole('button')).toHaveTextContent('Click me');
  });

  it('should call onClick when clicked', () => {
    const handleClick = jest.fn();
    render(<Button onClick={handleClick}>Click</Button>);

    fireEvent.click(screen.getByRole('button'));
    expect(handleClick).toHaveBeenCalledTimes(1);
  });

  it('should be disabled when disabled prop is true', () => {
    render(<Button disabled>Click</Button>);
    expect(screen.getByRole('button')).toBeDisabled();
  });

  it('should have correct variant class', () => {
    const { rerender } = render(<Button variant="primary">Click</Button>);
    expect(screen.getByRole('button')).toHaveClass('btn-primary');

    rerender(<Button variant="secondary">Click</Button>);
    expect(screen.getByRole('button')).toHaveClass('btn-secondary');
  });
});
```

## 前端检查清单 (Frontend Checklist)

### 功能性 (Functionality)

- [ ] 所有功能按设计规范工作
- [ ] 表单验证完整
- [ ] 错误处理和反馈清晰
- [ ] 导航流程正确
- [ ] 深度链接支持

### 性能 (Performance)

- [ ] Lighthouse 分数 >= 90
- [ ] 首次内容绘制 < 1.8s
- [ ] 最大内容绘制 < 2.5s
- [ ] 首次输入延迟 < 100ms
- [ ] 没有重排问题

### 安全性 (Security)

- [ ] 没有 XSS 漏洞
- [ ] CSRF 保护
- [ ] CSP 头部配置
- [ ] 依赖项无漏洞
- [ ] 敏感数据加密

### 可访问性 (Accessibility)

- [ ] WCAG 2.1 AA 合规
- [ ] 键盘可导航
- [ ] 屏幕阅读器支持
- [ ] 颜色对比度检查
- [ ] 焦点管理

### 浏览器兼容性 (Browser Compatibility)

- [ ] Chrome 最新两个版本
- [ ] Firefox 最新两个版本
- [ ] Safari 最新两个版本
- [ ] Edge 最新两个版本
- [ ] 移动浏览器支持

### 质量保证 (Quality Assurance)

- [ ] 单元测试 >= 80% 覆盖率
- [ ] 集成测试通过
- [ ] E2E 烟雾测试通过
- [ ] 代码审查批准
- [ ] 无 console 错误和警告
