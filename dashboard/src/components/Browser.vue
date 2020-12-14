
<template>
  <div class="db-browser">
    <input v-model="search" v-on:keyup.enter="filterOptions"/>
    <button @click="filterOptions">Search</button>
    <button @click="resetSearch">Reset Search</button>
    <button @click="cancel">Cancel</button>
    <div v-if="optionsLoading">
      Loading database...
    </div>
    <div v-else>
     <select size=20 v-model="selection" @change="loadSpec">
       <option v-for="(op, i) in selectOptions" :key="i">{{ op }}</option>
     </select>
     <div v-if="specLoading">
       Loading parameters...
     </div>
     <template v-else>
       <div v-if="this.spec">
         Parameters for Inverter : <b>{{this.selection }}</b><br />
         <ul class="parameter-summary">
           <li v-for="(v, k) in spec" :key="k">
             <b>{{ k }}:</b> {{ v }}
           </li>
         </ul>
         <button @click="commit">Use these parameters</button>
       </div>
       <div v-else>
         Please make a selection.
       </div>
     </template>
    </div>
  </div>
</template>
<script lang="ts">
import { Component, Prop, Vue, Watch } from "vue-property-decorator";

@Component
export default class DBBrowser extends Vue {
  @Prop() componentName!: string;
  optionsLoading = true;
  specLoading = false;
  options!: Array<string>;
  selectOptions: Array<string>= [];
  selection!: string;
  search!: string;
  spec: Record<string, any> = {};

  mounted() {
    this.loadOptions();
  }
  data() {
    return {
      show: false,
      options: this.options,
      selectOptions: this.options,
      selection: this.selection,
      spec: this.spec,
      search: this.search,
    };
  }
  async setFilteredOptions(){
    let opts: Array<string>;
    if (this.search && this.search != "") {
      opts = this.options.filter(x => x.includes(this.search));
    } else {
      opts = this.options;
    }
    return opts;
  }
  filterOptions(){
    this.optionsLoading = true;
    this.setFilteredOptions().then((opts) => {
      this.optionsLoading = false;
      this.selectOptions = opts;
    });
  }
  async loadOptions() {
    const token = await this.$auth.getTokenSilently();
    const response = await fetch(
      `/api/parameters/${this.componentName.toLowerCase()}`, {
        headers: new Headers({
          Authorization: `Bearer ${token}`
        })
    });
    const optionList = await response.json()
    this.options = optionList;
    this.selectOptions = optionList;
    this.optionsLoading = false;
  }
  resetSearch(){
    this.search = "";
    this.filterOptions();
  }
  async fetchSpec(){
    const token = await this.$auth.getTokenSilently();
    const response = await fetch(
      `/api/parameters/${this.componentName.toLowerCase()}/${this.selection}`, {
        headers: new Headers({
          Authorization: `Bearer ${token}`
        })
    });
    const optionList = await response.json();
    return optionList;
  }
  loadSpec() {
    this.specLoading = true;
    this.fetchSpec().then((spec) => {
      this.spec = spec;
      this.specLoading = false;
    });
  }
  commit() {
    this.$emit("parameters-selected", this.spec);
  }
  cancel() {
    this.$emit("cancel-selection");
  }
}
</script>

<style scoped>
div.db-browser {
  position: absolute;
  z-index: 10;
  background-color: white;
  border: solid 1px #333;
  padding: 1em;
}
.help-wrapper {
  position: absolute;
  padding: 0.5em;
  width: 300px;
  background-color: #fff;
  border: 1px solid black;
  border-radius: 5px;
  box-shadow: 1px 1px 5px #555;
  z-index: 1;
  top: 0;
  left: 100%;
}
</style>