<template>
  <div class="home">
    <h1>VizQL Multi-Agent</h1>
    <p>基于LangChain + LangGraph的多智能体查询与分析系统</p>
    <router-link to="/analysis">开始分析</router-link>
  </div>
</template>

<script setup lang="ts">
// Home页面
</script>

<style scoped>
.home {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100vh;
  text-align: center;
}

h1 {
  font-size: 3rem;
  margin-bottom: 1rem;
}

p {
  font-size: 1.2rem;
  color: #666;
  margin-bottom: 2rem;
}

a {
  padding: 1rem 2rem;
  background-color: #42b983;
  color: white;
  text-decoration: none;
  border-radius: 4px;
  font-size: 1.1rem;
  transition: background-color 0.3s;
}

a:hover {
  background-color: #359268;
}
</style>
