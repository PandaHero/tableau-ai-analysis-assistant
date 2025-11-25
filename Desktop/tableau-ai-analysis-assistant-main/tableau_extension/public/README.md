# Public Assets

这个目录包含Tableau Extension的公共资源文件。

## 文件说明

### tableau.extensions.1.latest.min.js
- **用途**: Tableau Extensions API v1库
- **来源**: 从statics文件夹移动而来
- **引用**: 在index.html中通过`<script>`标签引用
- **文档**: https://tableau.github.io/extensions-api/

### manifest.trex
- **用途**: Tableau Extension清单文件
- **说明**: 定义Extension的元数据、权限和配置
- **使用**: 在Tableau Desktop/Server中加载Extension时需要此文件

## 使用说明

### 开发环境

在开发环境中，Extension通过localhost访问：
```
http://localhost:5173
```

manifest.trex中的`<source-location>`指向开发服务器。

### 生产环境

在生产环境中，需要：
1. 构建项目：`npm run build`
2. 部署dist目录到Web服务器
3. 更新manifest.trex中的`<source-location>`为生产URL
4. 确保服务器支持HTTPS（Tableau要求）

### 在Tableau中加载Extension

1. 打开Tableau Desktop或Tableau Server
2. 在Dashboard中添加Extension对象
3. 选择"Access Local Extensions"
4. 选择manifest.trex文件
5. Extension将加载并显示在Dashboard中

## 注意事项

- Tableau Extensions API必须在Vue应用初始化之前加载
- 开发时使用HTTP，生产环境必须使用HTTPS
- manifest.trex文件必须与Extension一起部署
