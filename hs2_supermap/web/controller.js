(function(root){
  "use strict";
  const LAYERS=["stay","sale","business","auction"];
  class Controller{
    constructor(ports){
      for(const key of ["fetchSearch","fetchDetail","onResults","onDetail","onError"])
        if(typeof ports[key]!=="function")throw Error("Trusted controller ports required: "+key);
      this.ports=ports;this.layers=new Set(["stay"]);this.params={};
      this.selection=null;this.result=null;this.searchGeneration=0;this.detailGeneration=0;
    }
    query(){
      return {...this.params,layers:LAYERS.filter(k=>this.layers.has(k)).join(",")};
    }
    view(){
      return {layers:[...this.layers],selection:this.selection,params:{...this.params}};
    }
    clear(){
      this.detailGeneration++;if(this.detailAbort)this.detailAbort.abort();
      this.selection=null;this.ports.onDetail(null,this.view());
    }
    async search(params){
      this.params={...params};delete this.params.layers;
      const generation=++this.searchGeneration;
      if(this.searchAbort)this.searchAbort.abort();
      this.searchAbort=new AbortController();
      this.clear();this.result=null;this.ports.onResults(null,this.view());
      try{
        const result=await this.ports.fetchSearch(this.query(),this.searchAbort.signal);
        if(generation!==this.searchGeneration)return false;
        if(!result||result.ok!==true||!Array.isArray(result.items)||!Array.isArray(result.markers))
          throw Error(result?.code||"MAP_SOURCE_UNAVAILABLE");
        const items=result.items.filter(r=>this.layers.has(r.layer));
        const markers=result.markers.filter(r=>this.layers.has(r.layer));
        this.result={...result,items,markers};
        this.ports.onResults(this.result,this.view());return true;
      }catch(error){
        if(generation!==this.searchGeneration||error.name==="AbortError")return false;
        this.result=null;this.ports.onResults(null,this.view());
        this.ports.onError(error,this.view());return false;
      }
    }
    async toggle(layer,on){
      if(!LAYERS.includes(layer)||typeof on!=="boolean")throw Error("INVALID_LAYER");
      if(on)this.layers.add(layer);else this.layers.delete(layer);
      // An OFF never cascades to another layer. Fresh results clear stale panels.
      return this.search(this.params);
    }
    async select(layer,id){
      if(!this.layers.has(layer)||!this.result?.items.some(r=>r.layer===layer&&r.public_id===id))return false;
      const generation=++this.detailGeneration;
      if(this.detailAbort)this.detailAbort.abort();
      this.detailAbort=new AbortController();this.selection={layer,id};
      this.ports.onDetail(null,this.view());
      try{
        const result=await this.ports.fetchDetail(layer,id,this.query(),this.detailAbort.signal);
        if(generation!==this.detailGeneration||!this.layers.has(layer)
            ||this.selection?.layer!==layer||this.selection?.id!==id)return false;
        if(!result||result.ok!==true||result.item?.layer!==layer||result.item?.public_id!==id)
          throw Error(result?.code||"DETAIL_IDENTITY_MISMATCH");
        this.ports.onDetail(result.item,this.view());return true;
      }catch(error){
        if(generation!==this.detailGeneration||error.name==="AbortError")return false;
        this.clear();this.ports.onError(error,this.view());return false;
      }
    }
    async bounds(value){
      const bounds=Array.isArray(value)?value.join(","):value;
      if(bounds===this.params.bounds)return false;
      return this.search({...this.params,bounds});
    }
    async restore(saved){
      if(!saved||!Array.isArray(saved.layers)||saved.layers.some(k=>!LAYERS.includes(k)))throw Error("INVALID_RESTORED_LAYERS");
      this.layers=new Set(saved.layers);
      const pending=this.search(saved.params||{}),generation=this.searchGeneration;
      const success=await pending;
      if(success&&generation===this.searchGeneration&&saved.selection)
        return this.select(saved.selection.layer,saved.selection.id);
      return success;
    }
  }
  if(typeof module==="object"&&module.exports)module.exports=Controller;
  else root.HS2MapController=Controller;
})(typeof window==="object"?window:globalThis);
