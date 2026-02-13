# OnePro 代码仓库映射与分支规则

## 1) 仓库根地址
- HyperMotion: `http://192.168.10.254:20080/hypermotion/`
- Atomy: `http://192.168.10.254:20080/atomy/`

## 2) 模块 → 仓库路径映射
- newmuse → hypermotion/newmuse
- owl → hypermotion/owl
- crab → hypermotion/crab
- ant → hypermotion/ant
- porter → hypermotion/porter
- mistral → atomy/mistral
- atomy-unicloud → atomy/atomy-unicloud
- unicloud → hypermotion/unicloud
- atomy-obstor → atomy/atomy-obstor
- storplus → hypermotion/storplus
- oneway → hypermotion/oneway
- proxy → hypermotion/proxy
- minitgt → hypermotion/minitgt
- s3block → hypermotion/SwiftS3Block
- hamal → atomy/hamalv3
- Windows Agent → hypermotion/windows-agent
- Linux Agent / egisplus-agent → hypermotion/egisplus-agent

## 3) 分支选择规则
- 优先使用最新的 `HyperBDR_release_vx.x.x` 或 `HyperMotion_release_vx.x.x` 系列分支
- 若无匹配分支，则回退到 `master` 或 `main`

## 4) 认证
- Basic：用户名/密码
- 建议通过环境变量注入：`GIT_USER` / `GIT_PASS`
